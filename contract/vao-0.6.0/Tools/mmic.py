#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Offline MMIC contract and deterministic reference traces; no decoder execution."""

from __future__ import annotations

from bisect import bisect_right
import hashlib
from importlib import import_module
import io
import json
import math
from pathlib import Path
import base64
import subprocess
import sys
import struct
from typing import Callable

from jsonschema import Draft202012Validator, FormatChecker
import rfc8785

VERSION = "1.0.0"
PROFILE = f"https://w3id.org/modavis/vao/profile/mmic/{VERSION}"
NS = "https://w3id.org/modavis/vao/mmic#"
ONTOLOGY_VERSION = PROFILE + "/ontology"
LEVELS = ("documentation", "decoding", "comparison", "generation")
CAPABILITIES = {x: PROFILE + "/capability/" + x for x in LEVELS}
MAX_BYTES = 8 * 1024 * 1024
MAX_DEPTH = 32
MAX_RECORDS = 50000
MAX_MIDI_EVENTS = 100000
REGISTRIES = (
    "carriers",
    "states",
    "programmes",
    "parts",
    "observations",
    "features",
    "models",
    "assignments",
    "tracks",
    "roleAssignments",
    "interpretations",
    "playbacks",
    "comparisons",
    "designs",
    "fabrications",
    "evidence",
    "corrections",
)


class MMICError(ValueError):
    pass


class Unsupported(MMICError):
    pass


def resource_directory():
    root = Path(__file__).resolve().parent.parent
    source = root / "Profiles/MMIC" / VERSION
    if source.is_dir():
        return source
    return Path(import_module("vao_standard_mmic").__file__).parent


def digest(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    try:
        return rfc8785.dumps(value)
    except (ValueError, TypeError) as exc:
        raise MMICError(f"Unsafe canonical JSON: {exc}") from exc


def _domain(value, depth=0, counter=None):
    if counter is None:
        counter = [0]
    counter[0] += 1
    if counter[0] > 500000 or depth > MAX_DEPTH:
        raise MMICError("MMIC JSON structure exceeds its node/depth budget")
    if isinstance(value, float) and not math.isfinite(value):
        raise MMICError("Non-finite MMIC number")
    if (
        isinstance(value, int)
        and not isinstance(value, bool)
        and abs(value) > (1 << 53) - 1
    ):
        raise MMICError("MMIC integer outside the interoperable safe numeric domain")
    if isinstance(value, dict):
        for x in value.values():
            _domain(x, depth + 1, counter)
    elif isinstance(value, list):
        for x in value:
            _domain(x, depth + 1, counter)


def strict_json(data):
    if len(data) > MAX_BYTES:
        raise MMICError("MMIC asset exceeds the 8 MiB processing budget")

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise MMICError(f"Duplicate JSON key {key!r}")
            result[key] = value
        return result

    try:
        value = json.loads(
            data,
            object_pairs_hook=pairs,
            parse_constant=lambda x: (_ for _ in ()).throw(
                MMICError(f"Non-finite number {x}")
            ),
        )
        _domain(value)
        return value
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise MMICError(f"Invalid MMIC JSON: {exc}") from exc


def schema_errors(value):
    _domain(value)
    schema = json.loads((resource_directory() / "mmic.schema.json").read_text())
    return [
        f"MMIC-03 {'.'.join(map(str, x.path))}: {x.message}"
        for x in Draft202012Validator(
            schema, format_checker=FormatChecker()
        ).iter_errors(value)
    ]


def require(condition, requirement, message):
    if not condition:
        raise MMICError(f"{requirement}: {message}")


def increasing(values):
    return all(a < b for a, b in zip(values, values[1:]))


def interpolate(anchors, value, x="position", y="seconds"):
    xs = [a[x] for a in anchors]
    require(increasing(xs), "MMIC-08", "mapping inputs must increase strictly")
    require(
        xs[0] <= value <= xs[-1],
        "MMIC-08",
        "mapping does not cover the requested position",
    )
    i = min(max(bisect_right(xs, value) - 1, 0), len(anchors) - 2)
    a, b = anchors[i : i + 2]
    return a[y] + (value - a[x]) * (b[y] - a[y]) / (b[x] - a[x])


def model_digest(model):
    return digest(canonical(model["spec"]))


def coordinates(location, geometry):
    lo, hi = geometry["bounds"]
    a, b = location["start"], location["end"]
    period = geometry.get("period")
    if geometry["kind"] in {"cyclic", "cylindrical"}:
        require(
            period is not None and period > 0,
            "MMIC-07",
            "periodic geometry needs a positive period",
        )
        require(
            0 <= a < period and 0 <= b < period,
            "MMIC-07",
            "principal positions outside normalized period",
        )
        require(
            "startTurn" in location
            and "endTurn" in location
            and "wrapsSeam" in location,
            "MMIC-07",
            "periodic location needs turns and seam policy",
        )
        start_turn, end_turn = location["startTurn"], location["endTurn"]
        require(
            location["wrapsSeam"] == (start_turn != end_turn),
            "MMIC-07",
            "seam flag and turns disagree",
        )
        a += start_turn * period
        b += end_turn * period
    else:
        require(
            not any(k in location for k in ("startTurn", "endTurn", "wrapsSeam")),
            "MMIC-07",
            "linear location has cyclic fields",
        )
    require(
        lo <= a <= hi and lo <= b <= hi, "MMIC-07", "feature outside geometry bounds"
    )
    if geometry["kind"] == "cylindrical":
        require(
            "axialStart" in location and "axialEnd" in location,
            "MMIC-07",
            "cylindrical axial coordinates missing",
        )
        alo, ahi = geometry["axialBounds"]
        require(
            alo <= location["axialStart"] <= ahi and alo <= location["axialEnd"] <= ahi,
            "MMIC-07",
            "axial position outside declared bounds",
        )
    if location["kind"] == "point":
        require(
            a == b and location.get("axialStart") == location.get("axialEnd"),
            "MMIC-07",
            "point endpoints must coincide on every axis",
        )
    else:
        direction = 1 if geometry["direction"] == "forward" else -1
        require(
            direction * (b - a) > 0,
            "MMIC-07",
            "directed interval has nonpositive extent",
        )
    return a, b


def expected_event(feature, track, role, spec):
    a, b = coordinates(feature["location"], spec["geometry"])
    timing, reader = spec["timing"], spec["reader"]
    feature_a, feature_b = a, b
    a += role["readerOffset"]
    b += role["readerOffset"]
    start = interpolate(timing["anchors"], a) + reader["delaySeconds"]
    end = interpolate(timing["anchors"], b) + reader["delaySeconds"]
    kind = role["signalKind"]
    result = {"kind": kind, "onsetSeconds": start}
    if kind == "gate":
        result["durationSeconds"] = end - start
    elif kind == "latch":
        require(
            "value" in feature and "initialValue" in role,
            "MMIC-06",
            "latch needs explicit command and initial state",
        )
        result["value"] = feature["value"]
    elif kind == "envelope":
        require(
            "samples" in feature and "quantityUnit" in role,
            "MMIC-06",
            "envelope needs qualified samples/unit",
        )
        positions = [x["position"] for x in feature["samples"]]
        direction = 1 if spec["geometry"]["direction"] == "forward" else -1
        require(
            increasing([direction * p for p in positions])
            and min(feature_a, feature_b) <= min(positions)
            and max(positions) <= max(feature_a, feature_b),
            "MMIC-06",
            "envelope samples outside feature engagement",
        )
        result["unit"] = role["quantityUnit"]
        result["samples"] = [
            {
                "seconds": interpolate(
                    timing["anchors"], x["position"] + role["readerOffset"]
                )
                + reader["delaySeconds"],
                "value": x["value"],
            }
            for x in feature["samples"]
        ]
    return result


def _close(actual, expected, tolerance):
    if isinstance(expected, dict):
        return all(
            k in actual and _close(actual[k], v, tolerance) for k, v in expected.items()
        )
    if isinstance(expected, list):
        return (
            isinstance(actual, list)
            and len(actual) == len(expected)
            and all(_close(a, b, tolerance) for a, b in zip(actual, expected))
        )
    if isinstance(expected, (float, int)) and not isinstance(expected, bool):
        return (
            isinstance(actual, (int, float))
            and not isinstance(actual, bool)
            and abs(actual - expected) <= tolerance
        )
    return actual == expected


def _acyclic(records, field, requirement):
    by_id = {x["id"]: x for x in records}
    done = set()
    for record in records:
        chain = set()
        current = record
        while current["id"] not in done:
            require(
                current["id"] not in chain,
                requirement,
                "cyclic predecessor/supersession graph",
            )
            chain.add(current["id"])
            target = current.get(field)
            if target is None:
                break
            require(target in by_id, requirement, f"unknown predecessor {target}")
            if "carrierId" in record:
                require(
                    by_id[target]["carrierId"] == record["carrierId"],
                    requirement,
                    "state predecessors cross carrier identities",
                )
            current = by_id[target]
        done.update(chain)


def _vlq(stream):
    value = 0
    for _ in range(4):
        raw = stream.read(1)
        require(bool(raw), "MMIC-06", "truncated MIDI variable-length quantity")
        value = (value << 7) | (raw[0] & 127)
        if not raw[0] & 128:
            return value
    raise MMICError("MMIC-06: oversized MIDI variable-length quantity")


def midi_messages(data):
    """Parse bounded SMF 0/1 PPQN into exact tick/channel/command tuples.

    The reviewed binding uses one constant, initial tempo. Other legal SMF clock
    policies require another declared binding; they are not guessed here.
    """
    require(
        len(data) <= MAX_BYTES and data[:4] == b"MThd",
        "MMIC-06",
        "invalid/oversized SMF header",
    )
    stream = io.BytesIO(data)
    stream.seek(4)
    raw = stream.read(10)
    require(len(raw) == 10, "MMIC-06", "truncated SMF header")
    length, kind, count, division = struct.unpack(">IHHH", raw)
    require(
        length == 6 and count > 0 and count <= 128,
        "MMIC-06",
        "unsupported SMF header/track count",
    )
    if kind not in (0, 1) or division & 0x8000:
        raise Unsupported("MMIC-06: only SMF types 0/1 with PPQN are implemented")
    require(
        division > 0 and (kind != 0 or count == 1),
        "MMIC-06",
        "invalid SMF division or type-0 track count",
    )
    messages, tempos = [], []
    event_count = 0
    for _ in range(count):
        require(stream.read(4) == b"MTrk", "MMIC-06", "missing SMF track")
        raw = stream.read(4)
        require(len(raw) == 4, "MMIC-06", "missing SMF track size")
        size = struct.unpack(">I", raw)[0]
        body = stream.read(size)
        require(len(body) == size, "MMIC-06", "truncated SMF track")
        track = io.BytesIO(body)
        tick, running, ended = 0, None, False
        track_messages = []
        while track.tell() < size:
            event_count += 1
            require(
                event_count <= MAX_MIDI_EVENTS, "MMIC-15", "MIDI event budget exceeded"
            )
            tick += _vlq(track)
            raw = track.read(1)
            require(bool(raw), "MMIC-06", "truncated MIDI status")
            status = raw[0]
            if status < 128:
                require(running is not None, "MMIC-06", "invalid running status")
                track.seek(-1, 1)
                status = running
            if status == 255:
                running = None
                raw = track.read(1)
                require(bool(raw), "MMIC-06", "truncated MIDI meta event")
                meta = raw[0]
                meta_size = _vlq(track)
                payload = track.read(meta_size)
                require(
                    len(payload) == meta_size, "MMIC-06", "truncated MIDI meta payload"
                )
                if meta == 0x51:
                    require(meta_size == 3, "MMIC-06", "invalid MIDI tempo length")
                    tempos.append((tick, int.from_bytes(payload, "big")))
                if meta == 0x2F:
                    require(
                        meta_size == 0 and track.tell() == size,
                        "MMIC-06",
                        "invalid/mid-track MIDI end",
                    )
                    ended = True
                continue
            if status >= 0xF0:
                raise Unsupported(
                    "MMIC-06: system/SysEx messages are outside the initial SMF binding"
                )
            running = status
            command, channel = status >> 4, status & 15
            size_data = 1 if command in (12, 13) else 2
            values = track.read(size_data)
            require(
                len(values) == size_data and all(x < 128 for x in values),
                "MMIC-06",
                "invalid MIDI data bytes",
            )
            if command not in (8, 9, 11) or (command == 11 and values[0] >= 120):
                raise Unsupported(
                    "MMIC-06: MIDI command is outside the selected binding"
                )
            if command == 9 and values[1] == 0:
                command = 8
            message = (tick, command, channel, values[0], values[1])
            messages.append(message)
            track_messages.append(message)
        require(ended, "MMIC-06", "MIDI track lacks an end event")
        require(
            track_messages == sorted(track_messages),
            "MMIC-06",
            "SMF track violates canonical simultaneous-message ordering",
        )
    require(stream.read() == b"", "MMIC-06", "trailing bytes after SMF tracks")
    require(
        tempos and all(t == 0 and v == tempos[0][1] for t, v in tempos),
        "MMIC-06",
        "SMF binding requires a fixed explicit initial tempo",
    )
    return division, tempos[0][1], sorted(messages)


def export_messages(events, role_by_assignment, spec, binding_ids):
    bindings = {b["id"]: b for b in spec["exportBindings"]}
    require(
        set(binding_ids) <= set(bindings) and len(set(binding_ids)) == len(binding_ids),
        "MMIC-06",
        "unknown/duplicate export binding",
    )
    selected = [bindings[k] for k in binding_ids]
    require(bool(selected), "MMIC-06", "empty MIDI export binding selection")
    clocks = {(b["ticksPerBeat"], b["tempoMicroseconds"]) for b in selected}
    require(
        len(clocks) == 1, "MMIC-06", "selected bindings use incompatible SMF clocks"
    )
    division, tempo = next(iter(clocks))

    def tick(seconds):
        return round(seconds * 1e6 * division / tempo)

    result = []
    for binding in selected:
        role = next((r for r in spec["roles"] if r["id"] == binding["roleId"]), None)
        require(
            role is not None and binding["id"] in role["bindingIds"],
            "MMIC-06",
            "binding not selected by its authoritative role",
        )
        if binding["message"] == "control-change":
            require(
                role["role"] != "note" and role["role"] not in ("unknown", "guidance"),
                "MMIC-06",
                "nonfunctional/note role exported as controller",
            )
            require(
                "controller" in binding
                and "initialValue" in binding
                and "resetPolicy" in binding,
                "MMIC-06",
                "control binding lacks controller/state/reset policy",
            )
            known_controls = {NS + "Sustain": 64, NS + "SoftPedal": 67}
            if role.get("target") in known_controls:
                require(
                    binding["controller"] == known_controls[role["target"]],
                    "MMIC-06",
                    "known control function and MIDI controller disagree",
                )
            result.append(
                (
                    0,
                    11,
                    binding["channel"],
                    binding["controller"],
                    binding["initialValue"],
                )
            )
        else:
            require(
                role["role"] == "note" and "pitch" in binding and "velocity" in binding,
                "MMIC-06",
                "note binding requires a note role and declared pitch/velocity",
            )
        for event in events:
            if role_by_assignment[event["roleAssignmentId"]]["id"] != role["id"]:
                continue
            if binding["message"] == "note":
                require(
                    event["kind"] in ("gate", "impulse"),
                    "MMIC-06",
                    "note binding does not support this native signal",
                )
                policy = binding.get("durationPolicy", {})
                if policy.get("kind") == "engagement":
                    require(
                        event["kind"] == "gate",
                        "MMIC-06",
                        "impulse has no measured engagement note-off",
                    )
                    duration = event["durationSeconds"]
                else:
                    require(
                        policy.get("kind") == "fixed" and policy.get("seconds", 0) > 0,
                        "MMIC-06",
                        "impulse needs explicit export-duration policy",
                    )
                    duration = policy["seconds"]
                result += [
                    (
                        tick(event["onsetSeconds"]),
                        9,
                        binding["channel"],
                        binding["pitch"],
                        binding["velocity"],
                    ),
                    (
                        tick(event["onsetSeconds"] + duration),
                        8,
                        binding["channel"],
                        binding["pitch"],
                        0,
                    ),
                ]
            elif event["kind"] == "gate":
                require(
                    "onValue" in binding and "offValue" in binding,
                    "MMIC-06",
                    "gate binding needs set/release values",
                )
                result += [
                    (
                        tick(event["onsetSeconds"]),
                        11,
                        binding["channel"],
                        binding["controller"],
                        binding["onValue"],
                    ),
                    (
                        tick(event["onsetSeconds"] + event["durationSeconds"]),
                        11,
                        binding["channel"],
                        binding["controller"],
                        binding["offValue"],
                    ),
                ]
            elif event["kind"] == "latch":
                require(
                    0 <= event["value"] <= 127
                    and int(event["value"]) == event["value"],
                    "MMIC-06",
                    "latch command outside MIDI range",
                )
                result.append(
                    (
                        tick(event["onsetSeconds"]),
                        11,
                        binding["channel"],
                        binding["controller"],
                        int(event["value"]),
                    )
                )
            elif event["kind"] == "envelope":
                for sample in event["samples"]:
                    require(
                        0 <= sample["value"] <= 127
                        and int(sample["value"]) == sample["value"],
                        "MMIC-06",
                        "control curve requires a separate scaling binding",
                    )
                    result.append(
                        (
                            tick(sample["seconds"]),
                            11,
                            binding["channel"],
                            binding["controller"],
                            int(sample["value"]),
                        )
                    )
            else:
                raise Unsupported(
                    "MMIC-06: unresolved native actuation cannot be exported"
                )
        if binding.get("resetPolicy") == "explicit-final-reset":
            last = max((x[0] for x in result), default=0)
            result.append(
                (
                    last + 1,
                    11,
                    binding["channel"],
                    binding["controller"],
                    binding["initialValue"],
                )
            )
    return division, tempo, sorted(result)


def write_midi(division, tempo, messages):
    def vlq(n):
        values = [n & 127]
        n >>= 7
        while n:
            values.insert(0, (n & 127) | 128)
            n >>= 7
        return bytes(values)

    body = b"\0\xff\x51\x03" + tempo.to_bytes(3, "big")
    previous = 0
    for tick, command, channel, first, second in sorted(messages):
        body += vlq(tick - previous) + bytes([(command << 4) | channel, first, second])
        previous = tick
    body += b"\0\xff\x2f\0"
    return (
        b"MThd"
        + struct.pack(">IHHH", 6, 0, 1, division)
        + b"MTrk"
        + struct.pack(">I", len(body))
        + body
    )


def validate_subjects(data, manifest):
    ext = manifest.get("extensions", {}).get(PROFILE)
    if ext is None:
        return
    represented = (
        {c["id"] for c in data["carriers"]}
        | {c["digitalEntityId"] for c in data["carriers"]}
        | {d["id"] for d in data["designs"]}
    )
    require(
        set(ext["subjectEntityIds"]) <= represented,
        "MMIC-02",
        "claimed subjects are absent from the MMIC carrier/surrogate/design records",
    )


def validate_domain(
    data, manifest, read_asset: Callable[[str], bytes | dict | None], exercised=None
):
    """Validate already fixed core declarations and locally available assets."""
    errors = schema_errors(data)
    if errors:
        raise MMICError("; ".join(errors[:20]))
    validate_subjects(data, manifest)
    require(
        sum(len(data[k]) for k in REGISTRIES) <= MAX_RECORDS,
        "MMIC-15",
        "MMIC record budget exceeded",
    )
    levels = set(data["levels"])
    require(
        "documentation" in levels
        and ("comparison" not in levels or "decoding" in levels),
        "MMIC-12",
        "invalid level dependency",
    )
    by = {k: {x["id"]: x for x in data[k]} for k in REGISTRIES}
    records = [x for k in REGISTRIES for x in data[k]]
    nested = [
        x
        for m in data["models"]
        for x in m["spec"]["roles"] + m["spec"]["exportBindings"]
    ]
    nested += [x for i in data["interpretations"] for x in i["events"]]
    all_records = records + nested + [{"id": data["id"]}]
    ids = [r["id"] for r in all_records]
    require(
        len(ids) == len(set(ids)),
        "MMIC-01",
        "IDs collide across domain registries, model roles/bindings or events",
    )
    known = set(ids)
    core_entities = {x["id"]: x for x in manifest["entities"]}
    assets = {x["id"]: x for x in manifest["realizations"]}
    agents = {x["id"] for x in manifest["scientific"]["agents"]}
    activities = {x["id"]: x for x in manifest["scientific"]["activities"]}
    core_ids = set()

    def core_identifiers(value):
        if isinstance(value, dict):
            if isinstance(value.get("id"), str):
                core_ids.add(value["id"])
            for key, child in value.items():
                if key not in ("extensions", "properties", "parameterValues"):
                    core_identifiers(child)
        elif isinstance(value, list):
            for child in value:
                core_identifiers(child)

    core_identifiers(manifest)
    allowed_reuse = set(by["carriers"]) | set(by["designs"])
    require(
        (known & core_ids) <= allowed_reuse,
        "MMIC-01",
        "domain event/record reuses a different core identity",
    )

    def get(registry, identifier):
        require(
            identifier in by[registry],
            "MMIC-01",
            f"reference {identifier} does not resolve to {registry}",
        )
        return by[registry][identifier]

    def raw(identifier, needed=True):
        require(
            identifier in assets, "MMIC-03", f"unknown core realization {identifier}"
        )
        value = read_asset(identifier)
        if value is None:
            if needed:
                raise Unsupported(
                    f"MMIC-14: required realization is unavailable: {identifier}"
                )
            return None
        if isinstance(value, dict):
            expected_proof = {
                "coreVerified": True,
                "sha256": assets[identifier]["sha256"],
                "byteSize": assets[identifier]["byteSize"],
            }
            media = assets[identifier]["mediaType"]
            require(
                value == expected_proof
                and (
                    media.startswith("image/")
                    or (media.startswith("audio/") and media != "audio/midi")
                ),
                "MMIC-03",
                "untrusted/non-opaque core availability proof",
            )
            return value
        require(
            assets[identifier]["byteSize"] <= MAX_BYTES,
            "MMIC-15",
            "asset exceeds bounded domain parser budget",
        )
        require(
            len(value) == assets[identifier]["byteSize"]
            and digest(value) == assets[identifier]["sha256"],
            "MMIC-03",
            "asset bytes differ from exact core realization",
        )
        return value

    for record in records:
        for eid in record.get("evidenceIds", []):
            get("evidence", eid)
    rights = {r["id"]: r for r in manifest["rights"]}
    for redaction in data.get("redactions", []):
        identifier = redaction["realizationId"]
        require(
            identifier in assets
            and any(
                rights[r]["access"] in ("restricted", "embargoed", "closed")
                for r in assets[identifier]["rightsIds"]
            ),
            "MMIC-15",
            "redaction lacks a restricted core realization and rights basis",
        )
        require(
            read_asset(identifier) is None,
            "MMIC-15",
            "redacted bytes are embedded in this carrier",
        )
    require(bool(data["evidence"]), "MMIC-09", "documentary evidence is required")
    for evidence in data["evidence"]:
        require(
            evidence["agentId"] in agents,
            "MMIC-09",
            "evidence responsibility does not resolve to a core Agent",
        )
        if "sourceRealizationId" in evidence:
            raw(evidence["sourceRealizationId"], False)
        if "fragmentBounds" in evidence:
            require(
                evidence["fragmentBounds"][0] <= evidence["fragmentBounds"][1],
                "MMIC-09",
                "source fragment bounds reversed",
            )
    for registry in ("states", "models", "interpretations"):
        _acyclic(data[registry], "predecessorId", "MMIC-01")
    require(
        bool(data["carriers"] or data["designs"]),
        "MMIC-02",
        "no physical carrier or design subject",
    )
    for carrier in data["carriers"]:
        require(
            carrier["id"] in core_entities
            and NS + "PhysicalCarrier" in core_entities[carrier["id"]]["types"],
            "MMIC-02",
            "physical carrier needs its own correctly typed core entity",
        )
        require(
            carrier["digitalEntityId"] in core_entities
            and carrier["digitalEntityId"] != carrier["id"]
            and NS + "DigitalCarrier"
            in core_entities[carrier["digitalEntityId"]]["types"],
            "MMIC-01",
            "physical/digital identities conflated or untyped",
        )
        require(
            any(s["carrierId"] == carrier["id"] for s in data["states"]),
            "MMIC-02",
            "physical carrier lacks a qualified state/geometry/coverage",
        )
        if carrier["origin"] == "generated":
            require(
                any(f["carrierId"] == carrier["id"] for f in data["fabrications"]),
                "MMIC-11",
                "generated physical carrier lacks fabrication lineage",
            )
    for state in data["states"]:
        get("carriers", state["carrierId"])
        geometry = state["geometry"]
        if geometry["kind"] != "undetermined":
            require(
                geometry["bounds"][0] < geometry["bounds"][1],
                "MMIC-07",
                "empty geometry domain",
            )
        if geometry["kind"] == "cylindrical":
            require(
                "axialBounds" in geometry
                and "axialUnit" in geometry
                and geometry["axialBounds"][0] < geometry["axialBounds"][1],
                "MMIC-07",
                "cylindrical geometry lacks axial domain/units",
            )
        if state.get("changeKind") == "physical-intervention":
            require(
                state.get("interventionActivityId") in activities,
                "MMIC-01",
                "physical intervention lacks a core activity",
            )
    for part in data["parts"]:
        get("states", part["stateId"])
        require(
            all(x in by["parts"] for x in part.get("joins", [])),
            "MMIC-07",
            "unknown part join",
        )
    for programme in data["programmes"]:
        state = get("states", programme["stateId"])
        if programme["extent"] is None:
            require(
                state["geometry"]["kind"] == "undetermined",
                "MMIC-07",
                "unknown programme extent needs qualified unknown geometry",
            )
        else:
            lo, hi = programme["extent"]
            require(
                "bounds" in state["geometry"]
                and state["geometry"]["bounds"][0]
                <= lo
                < hi
                <= state["geometry"]["bounds"][1],
                "MMIC-07",
                "programme extent outside carrier domain",
            )
        for part in programme.get("partIds", []):
            require(
                get("parts", part)["stateId"] == state["id"],
                "MMIC-07",
                "programme part belongs to another state",
            )
        sequences = [get("parts", x)["sequence"] for x in programme.get("partIds", [])]
        require(
            increasing(sequences),
            "MMIC-07",
            "programme parts are not in unique declared order",
        )
    for observation in data["observations"]:
        get("states", observation["stateId"])
        require(
            observation["sourceRealizationId"] in assets
            and observation["activityId"] in activities,
            "MMIC-09",
            "observation source/activity unresolved",
        )
        require(
            all(a < b for a, b in observation["sourceBounds"]),
            "MMIC-05",
            "invalid source observation bounds",
        )
    for feature in data["features"]:
        state = get("states", feature["stateId"])
        observation = get("observations", feature["observationId"])
        require(
            observation["stateId"] == feature["stateId"]
            and get("programmes", feature["programmeId"])["stateId"]
            == feature["stateId"],
            "MMIC-05",
            "feature observation/programme belongs to another state",
        )
        coordinates(feature["location"], state["geometry"])
        require(
            len(feature["selector"]) == len(observation["sourceBounds"])
            and all(
                lo <= a <= b <= hi
                for (a, b), (lo, hi) in zip(
                    feature["selector"], observation["sourceBounds"]
                )
            ),
            "MMIC-05",
            "feature selector outside source bounds",
        )
        get("tracks", feature["trackId"])
    for model in data["models"]:
        spec = model["spec"]
        require(
            model_digest(model) == model["specSHA256"],
            "MMIC-04",
            "complete operational model digest is stale",
        )
        for pin in spec["artifactPins"]:
            require(
                pin["realizationId"] in assets
                and assets[pin["realizationId"]]["sha256"] == pin["sha256"],
                "MMIC-04",
                "model artifact pin disagrees with core fixity",
            )
        runtime = spec["runtime"]
        pins = {x["realizationId"] for x in spec["artifactPins"]}
        require(
            {runtime["codeRealizationId"], runtime["environmentRealizationId"]} <= pins,
            "MMIC-04",
            "model does not bind code/environment bytes",
        )
        anchors = spec["timing"]["anchors"]
        direction = 1 if spec["geometry"]["direction"] == "forward" else -1
        require(
            increasing([a["position"] for a in anchors])
            and increasing([direction * a["seconds"] for a in anchors]),
            "MMIC-08",
            "clock anchors disagree with transport direction",
        )
        require(
            spec["timing"]["unit"] == spec["geometry"].get("unit"),
            "MMIC-08",
            "clock coordinate units differ from geometry",
        )
        indices = [r["trackIndex"] for r in spec["roles"]]
        require(
            len(indices) == len(set(indices)),
            "MMIC-05",
            "model assigns multiple roles to one track index",
        )
        bindings = {b["id"]: b for b in spec["exportBindings"]}
        for role in spec["roles"]:
            require(
                role["readerOffsetUnit"] == spec["geometry"].get("unit"),
                "MMIC-07",
                "reader offset units differ from geometry",
            )
            require(
                set(role["bindingIds"]) <= set(bindings)
                and all(
                    bindings[b]["roleId"] == role["id"] for b in role["bindingIds"]
                ),
                "MMIC-06",
                "role/export-binding ownership mismatch",
            )
            if role["role"] in ("unknown", "guidance"):
                require(
                    not role["bindingIds"] and role["signalKind"] == "unresolved",
                    "MMIC-05",
                    "unknown/guidance role has playable fallback",
                )
    track_keys = [(t["modelId"], t["index"]) for t in data["tracks"]]
    require(
        len(track_keys) == len(set(track_keys)),
        "MMIC-05",
        "duplicate model track index",
    )
    for track in data["tracks"]:
        spec = get("models", track["modelId"])["spec"]
        require(
            any(r["trackIndex"] == track["index"] for r in spec["roles"]),
            "MMIC-05",
            "track has wrong model index/coordinate unit",
        )
    for assignment in data["assignments"]:
        get("models", assignment["modelId"])
        if "stateId" in assignment:
            state = get("states", assignment["stateId"])
            require(
                get("models", assignment["modelId"])["spec"]["geometry"]
                == state["geometry"],
                "MMIC-04",
                "model geometry differs from its selected state",
            )
        if "programmeId" in assignment:
            require(
                get("programmes", assignment["programmeId"])["stateId"]
                == assignment.get("stateId"),
                "MMIC-05",
                "assignment programme/state mismatch",
            )
    role_by_assignment = {}
    for assignment in data["roleAssignments"]:
        owner = get("assignments", assignment["assignmentId"])
        model = get("models", owner["modelId"])
        role = next(
            (r for r in model["spec"]["roles"] if r["id"] == assignment["modelRoleId"]),
            None,
        )
        track = get("tracks", assignment["trackId"])
        require(
            role is not None
            and track["modelId"] == model["id"]
            and track["index"] == role["trackIndex"],
            "MMIC-05",
            "role assignment/model track mismatch",
        )
        role_by_assignment[assignment["id"]] = role
    executable = bool(levels & {"decoding", "comparison", "generation"})
    if executable:
        require(bool(data["models"]), "MMIC-04", "executable level lacks a model")
    for model in data["models"]:
        spec = model["spec"]
        if not executable:
            continue
        if (
            spec["reader"]["segmented"]
            or spec["geometry"]["kind"] == "undetermined"
            or spec["geometry"]["direction"] == "undetermined"
            or spec["timing"]["calibrationStatus"] == "uncalibrated"
        ):
            raise Unsupported(
                "MMIC-07/08: segmented/undetermined/uncalibrated execution requires another reference algorithm"
            )
        for pin in spec["artifactPins"]:
            raw(pin["realizationId"])
        lo, hi = spec["reader"]["domain"]
        require(
            lo <= hi
            and spec["geometry"]["bounds"][0] <= lo
            and hi <= spec["geometry"]["bounds"][1],
            "MMIC-07",
            "reader domain outside geometry",
        )
        if spec["geometry"]["kind"] == "cylindrical":
            path = spec["reader"]["trajectory"]
            require(
                len(path) >= 2
                and spec["reader"]["interpolation"] == "linear"
                and increasing([x["position"] for x in path]),
                "MMIC-07",
                "helical reader lacks an ordered interpolated path",
            )
            require(
                path[0]["position"] <= lo and path[-1]["position"] >= hi,
                "MMIC-07",
                "reader path does not cover its full declared domain",
            )
            alo, ahi = spec["geometry"]["axialBounds"]
            require(
                all(alo <= x["axial"] <= ahi for x in path),
                "MMIC-07",
                "reader path leaves axial domain",
            )
    if "decoding" in levels:
        require(
            any(i["sourceKind"] == "carrier-derived" for i in data["interpretations"]),
            "MMIC-12",
            "decoding has no carrier-derived interpretation",
        )
    for interpretation in data["interpretations"]:
        model = get("models", interpretation["modelId"])
        spec = model["spec"]
        assignment = get("assignments", interpretation["assignmentId"])
        require(
            assignment["modelId"] == model["id"]
            and assignment["status"] in ("accepted", "hypothesis")
            and assignment["selected"],
            "MMIC-05",
            "interpretation uses unselected/rejected model",
        )
        require(
            interpretation["modelSHA256"]
            == model["specSHA256"]
            == interpretation["execution"]["modelSHA256"],
            "MMIC-04",
            "interpretation does not bind exact complete model",
        )
        execution = interpretation["execution"]
        require(
            execution["activityId"] in activities
            and execution["codeRealizationId"] == spec["runtime"]["codeRealizationId"]
            and execution["environmentRealizationId"]
            == spec["runtime"]["environmentRealizationId"],
            "MMIC-09",
            "execution code/environment/activity mismatch",
        )
        require(
            set(interpretation["sourceRealizationIds"]) <= set(assets),
            "MMIC-09",
            "interpretation source does not resolve",
        )
        for rid in interpretation["sourceRealizationIds"]:
            raw(rid, executable)
        events = interpretation["events"]
        require(
            increasing([e["onsetSeconds"] for e in events])
            or all(
                a <= b
                for a, b in zip(
                    [e["onsetSeconds"] for e in events],
                    [e["onsetSeconds"] for e in events][1:],
                )
            ),
            "MMIC-06",
            "native events are unordered",
        )
        included = set()
        for event in events:
            role_assignment = get("roleAssignments", event["roleAssignmentId"])
            role = role_by_assignment[event["roleAssignmentId"]]
            require(
                role_assignment["assignmentId"] == assignment["id"]
                and role_assignment["status"] in ("accepted", "hypothesis"),
                "MMIC-05",
                "event uses rejected/other assignment",
            )
            require(
                role["role"] not in ("guidance", "unknown")
                and event["kind"] == role["signalKind"],
                "MMIC-06",
                "event signal disagrees with functional role",
            )
            if interpretation["sourceKind"] == "carrier-derived":
                require(
                    len(event["sourceFeatureIds"]) == 1,
                    "MMIC-05",
                    "reference trace requires one source feature per event",
                )
                feature = get("features", event["sourceFeatureIds"][0])
                require(
                    feature["trackId"] == role_assignment["trackId"]
                    and feature["stateId"] == assignment.get("stateId")
                    and feature["programmeId"] == assignment.get("programmeId"),
                    "MMIC-05",
                    "event source track/state/programme mismatch",
                )
                require(
                    feature["kind"] not in ("print", "damage", "unknown"),
                    "MMIC-05",
                    "non-actuating observation emits signal",
                )
                a, b = coordinates(feature["location"], spec["geometry"])
                track = get("tracks", feature["trackId"])
                programme = get("programmes", feature["programmeId"])
                require(
                    spec["reader"]["domain"][0] <= min(a, b)
                    and max(a, b) <= spec["reader"]["domain"][1]
                    and programme["extent"][0] <= min(a, b)
                    and max(a, b) <= programme["extent"][1],
                    "MMIC-07",
                    "reader/programme domain does not cover an event",
                )
                if spec["geometry"]["kind"] == "cylindrical":
                    path = spec["reader"]["trajectory"]
                    require(
                        abs(
                            interpolate(path, a, y="axial")
                            - feature["location"]["axialStart"]
                        )
                        <= 1e-9
                        and abs(
                            interpolate(path, b, y="axial")
                            - feature["location"]["axialEnd"]
                        )
                        <= 1e-9,
                        "MMIC-07",
                        "feature does not intersect the selected helical reader trajectory",
                    )
                expected = expected_event(feature, track, role, spec)
                require(
                    _close(event, expected, spec["timing"]["toleranceSeconds"]),
                    "MMIC-08",
                    "native event differs from recomputed reader/timing response",
                )
                included.add(feature["id"])
            else:
                require(
                    not event["sourceFeatureIds"],
                    "MMIC-05",
                    "audio/simulation event falsely names physical source features",
                )
        excluded = set(interpretation["excludedFeatureIds"])
        require(
            excluded <= set(by["features"]) and not included & excluded,
            "MMIC-05",
            "excluded feature unknown or also interpreted",
        )
        if interpretation["sourceKind"] == "carrier-derived":
            scope = {
                f["id"]
                for f in data["features"]
                if f["programmeId"] == assignment["programmeId"]
            }
            require(
                scope == included | excluded,
                "MMIC-05",
                "observed feature coverage is not fully accounted for",
            )
        if executable:
            require(
                strict_json(raw(interpretation["nativeRealizationId"])) == events,
                "MMIC-06",
                "native asset differs from declared events",
            )
            for exported in interpretation["exports"]:
                expected = export_messages(
                    events, role_by_assignment, spec, exported["bindingIds"]
                )
                require(
                    midi_messages(raw(exported["realizationId"])) == expected,
                    "MMIC-06",
                    "role/binding/native-event/SMF bytes disagree",
                )
                require(
                    bool(exported["losses"]),
                    "MMIC-06",
                    "MIDI export lacks an explicit loss/assumption report",
                )
    if "comparison" in levels:
        require(
            bool(data["comparisons"]), "MMIC-12", "comparison level has no comparison"
        )
    for playback in data["playbacks"]:
        require(
            playback["operatorAgentId"] in agents
            and playback["recordingRealizationId"] in assets,
            "MMIC-10",
            "playback operator/recording unresolved",
        )
        if playback["recordingKind"] == "physical":
            require(
                playback.get("instrumentId") in core_entities
                and playback.get("stateId") in by["states"]
                and playback.get("programmeId") in by["programmes"],
                "MMIC-10",
                "physical take lacks instrument/state/programme",
            )
            require(
                not assets[playback["recordingRealizationId"]]
                .get("extensions", {})
                .get(NS + "synthetic", False),
                "MMIC-10",
                "simulated recording masquerades as physical take",
            )
    for comparison in data["comparisons"]:
        left = get("interpretations", comparison["leftInterpretationId"])
        right = get("interpretations", comparison["rightInterpretationId"])
        playback = get("playbacks", comparison["playbackId"])
        require(
            left["id"] != right["id"]
            and not set(left["sourceRealizationIds"])
            & set(right["sourceRealizationIds"])
            and playback["recordingRealizationId"] in right["sourceRealizationIds"],
            "MMIC-10",
            "comparison sources are not independent or not the recorded take",
        )
        require(
            playback["recordingKind"] != "unknown"
            and (
                not data["synthetic"]
                or comparison["referenceStatus"] == "synthetic-test"
            ),
            "MMIC-10",
            "comparison makes an unqualified reference claim",
        )
        alignment = comparison["alignment"]
        require(
            strict_json(raw(comparison["alignmentRealizationId"])) == alignment,
            "MMIC-10",
            "alignment artifact differs from declaration",
        )
        anchors = alignment["anchors"]
        require(
            increasing([a["left"] for a in anchors])
            and increasing([a["right"] for a in anchors]),
            "MMIC-10",
            "alignment is non-monotonic",
        )
        lo, hi = alignment["domain"]
        require(
            anchors[0]["left"] <= lo < hi <= anchors[-1]["left"],
            "MMIC-10",
            "alignment domain lacks anchor coverage",
        )
        le = {e["id"]: e for e in left["events"]}
        re = {e["id"]: e for e in right["events"]}
        residuals, left_used, right_used = [], set(), set()
        for pair in comparison["pairs"]:
            a, b = pair["leftEventId"], pair["rightEventId"]
            require(
                a in le and b in re and a not in left_used and b not in right_used,
                "MMIC-10",
                "comparison pair is unknown or reused",
            )
            require(
                le[a]["kind"] == re[b]["kind"] and lo <= le[a]["onsetSeconds"] <= hi,
                "MMIC-10",
                "paired event kind/domain disagrees",
            )
            residuals.append(
                abs(
                    interpolate(anchors, le[a]["onsetSeconds"], "left", "right")
                    - re[b]["onsetSeconds"]
                )
            )
            left_used.add(a)
            right_used.add(b)
        require(
            set(le) == left_used | set(alignment["unmatchedLeftEventIds"])
            and set(re) == right_used | set(alignment["unmatchedRightEventIds"])
            and not left_used & set(alignment["unmatchedLeftEventIds"])
            and not right_used & set(alignment["unmatchedRightEventIds"]),
            "MMIC-10",
            "comparison silently omits events",
        )
        if alignment["gapPolicy"] == "none":
            require(
                not alignment["unmatchedLeftEventIds"]
                and not alignment["unmatchedRightEventIds"],
                "MMIC-10",
                "gap-free alignment contains unmatched events",
            )
        coverage = len(left_used) / max(1, len(le))
        residual = max(residuals, default=0)
        require(
            abs(comparison["metrics"]["matchedCoverage"] - coverage) < 1e-12
            and abs(comparison["metrics"]["maxResidualSeconds"] - residual) < 1e-9
            and residual <= alignment["toleranceSeconds"],
            "MMIC-10",
            "comparison metrics/declared tolerance disagree with actual pairs",
        )
    if "generation" in levels:
        require(bool(data["designs"]), "MMIC-12", "generation level has no design")
    for design in data["designs"]:
        require(
            design["id"] in core_entities
            and NS + "CarrierDesign" in core_entities[design["id"]]["types"],
            "MMIC-02",
            "design-only subject lacks a correctly typed core entity",
        )
        model = get("models", design["modelId"])
        require(
            design["execution"]["modelSHA256"] == model["specSHA256"]
            and design["execution"]["activityId"] in activities
            and design["execution"]["codeRealizationId"]
            == model["spec"]["runtime"]["codeRealizationId"]
            and design["execution"]["environmentRealizationId"]
            == model["spec"]["runtime"]["environmentRealizationId"],
            "MMIC-11",
            "design execution/model/activity mismatch",
        )
        if "generation" in levels:
            validate_generation(design, model, raw)
        else:
            require(
                {
                    design["sourceRealizationId"],
                    design["layoutRealizationId"],
                    design["reportRealizationId"],
                }
                <= set(assets),
                "MMIC-02",
                "design documentary source/layout/report missing",
            )
        if design["fabricationStatus"] == "fabricated":
            require(
                any(f["designId"] == design["id"] for f in data["fabrications"]),
                "MMIC-11",
                "fabricated design has no fabrication record",
            )
    for fabrication in data["fabrications"]:
        design = get("designs", fabrication["designId"])
        carrier = get("carriers", fabrication["carrierId"])
        state = get("states", fabrication["stateId"])
        require(
            design["fabricationStatus"] == "fabricated"
            and carrier["origin"] == "generated"
            and state["carrierId"] == carrier["id"]
            and fabrication["activityId"] in activities
            and fabrication["measuredGeometry"] == state["geometry"],
            "MMIC-11",
            "fabrication does not connect fixed design to inspected physical state",
        )
        require(
            fabrication["measuredGeometry"]["status"]
            in ("measured", "estimated", "undetermined"),
            "MMIC-11",
            "intended geometry substituted for inspected state",
        )
        inspection = raw(fabrication["inspectionRealizationId"], executable)
        if inspection is not None:
            require(
                strict_json(inspection) == fabrication["measuredGeometry"],
                "MMIC-11",
                "inspection bytes disagree with manufactured geometry",
            )
    for correction in data["corrections"]:
        previous = get("interpretations", correction["previousInterpretationId"])
        replacement = get("interpretations", correction["replacementInterpretationId"])
        old_targets = {r["id"]: r for r in [previous, *previous["events"]]}
        new_targets = {r["id"]: r for r in [replacement, *replacement["events"]]}
        require(
            correction["targetId"] in old_targets
            and correction["replacementTargetId"] in new_targets
            and correction["replacementTargetId"] != correction["targetId"]
            and correction["agentId"] in agents
            and replacement.get("predecessorId")
            == correction["previousInterpretationId"],
            "MMIC-10",
            "correction lacks immutable target/agent/replacement lineage",
        )
        before, after = correction["previousValue"], correction["replacementValue"]
        require(
            bool(before)
            and set(before) == set(after)
            and before != after
            and all(
                old_targets[correction["targetId"]].get(k) == v
                for k, v in before.items()
            )
            and all(
                new_targets[correction["replacementTargetId"]].get(k) == v
                for k, v in after.items()
            ),
            "MMIC-10",
            "correction values do not match retained exact targets",
        )
    if exercised is not None:
        exercised.extend(
            ["CORE-01", "CORE-02"]
            + [f"MMIC-{i:02d}" for i in (1, 2, 3, 4, 5, 9, 12, 13, 14, 15)]
        )
        if executable:
            exercised.extend(["MMIC-06", "MMIC-07", "MMIC-08"])
        if data["comparisons"] or data["corrections"] or data["playbacks"]:
            exercised.append("MMIC-10")
        if data["designs"] or data["fabrications"]:
            exercised.append("MMIC-11")
    return {
        "status": "valid",
        "levels": sorted(levels),
        "historicalCertification": "not established",
    }


def validate_generation(design, model, raw):
    spec = model["spec"]
    if spec["geometry"]["kind"] != "linear" or spec["reader"]["segmented"]:
        raise Unsupported(
            "MMIC-11: reference generation supports unsegmented linear layouts"
        )
    division, tempo, commands = midi_messages(raw(design["sourceRealizationId"]))
    report = strict_json(raw(design["reportRealizationId"]))
    layout = strict_json(raw(design["layoutRealizationId"]))
    require(
        isinstance(report, dict) and isinstance(layout, dict),
        "MMIC-11",
        "generation artifacts are not records",
    )
    require(
        report.get("sourceSHA256") == digest(raw(design["sourceRealizationId"]))
        and report.get("modelSHA256") == model["specSHA256"],
        "MMIC-11",
        "generation report has stale input/model pins",
    )
    constraints = spec["constraints"]
    pitches = [x[3] for x in commands if x[1] == 9]
    unsupported = [
        list(x)
        for x in commands
        if x[1] == 11
        or (
            x[1] == 9
            and not constraints["minimumTarget"] <= x[3] <= constraints["maximumTarget"]
        )
    ]
    exclusions = report.get("excludedCommands", [])
    require(
        exclusions == unsupported
        and (
            not unsupported or constraints["unsupportedPolicy"] == "explicit-exclusions"
        ),
        "MMIC-11",
        "unsupported target/control silently adapted or clipped",
    )
    require(
        report.get("adaptations") == [] and report.get("fabricated") is False,
        "MMIC-11",
        "reference layout cannot claim unimplemented adaptation/fabrication",
    )
    require(
        layout.get("modelSHA256") == model["specSHA256"]
        and layout.get("sourceSHA256") == report["sourceSHA256"],
        "MMIC-11",
        "layout lineage differs from generation report",
    )
    starts = {}
    expected = []
    previous = {}
    for tick, command, channel, pitch, velocity in commands:
        if [tick, command, channel, pitch, velocity] in unsupported or not constraints[
            "minimumTarget"
        ] <= pitch <= constraints["maximumTarget"]:
            continue
        seconds = tick * tempo / division / 1e6
        key = (channel, pitch)
        if command == 9:
            require(
                key not in starts,
                "MMIC-11",
                "overlapping generation commands require an explicit voice policy",
            )
            require(
                seconds - previous.get(key, -1e12)
                >= constraints["minimumRepeatSeconds"],
                "MMIC-11",
                "target repetition constraint violated",
            )
            starts[key] = seconds
            previous[key] = seconds
        elif command == 8:
            require(
                key in starts and seconds > starts[key],
                "MMIC-11",
                "orphan/zero-duration source note",
            )
            start = starts.pop(key)
            anchors = spec["timing"]["anchors"]
            ordered = sorted(anchors, key=lambda a: a["seconds"])
            a = interpolate(ordered, start, "seconds", "position")
            b = interpolate(ordered, seconds, "seconds", "position")
            require(
                abs(b - a) >= constraints["minimumClearance"],
                "MMIC-11",
                "generated mark fails material/tool clearance",
            )
            expected.append({"channel": channel, "target": pitch, "start": a, "end": b})
    require(
        not starts and bool(pitches), "MMIC-11", "unfinished/empty generation input"
    )
    require(
        layout.get("commands") == expected
        and report.get("acceptedCount") == len(expected),
        "MMIC-11",
        "layout/report differs from recomputed source instructions",
    )


def manifest_contract(manifest):
    """Inspect exact known profile declarations without acquiring domain assets."""
    extensions = manifest.get("extensions", {})
    matching = [
        x
        for x in extensions
        if x.startswith("https://w3id.org/modavis/vao/profile/mmic/")
    ]
    records = [
        r
        for k in ("profiles", "materializableProfiles")
        for r in manifest.get(k, [])
        if r.get("id") == PROFILE
    ]
    if matching and PROFILE not in matching and not records:
        raise Unsupported("MMIC-13: unimplemented MMIC profile version is preserved")
    if not matching and not records and PROFILE not in manifest.get("conformsTo", []):
        return None
    require(
        matching == [PROFILE]
        and len(records) == 1
        and PROFILE in manifest["conformsTo"],
        "MMIC-13",
        "MMIC profile is absent, duplicated, conflicting or unsupported",
    )
    ext, record = extensions[PROFILE], records[0]
    fields = {
        "profileVersion",
        "ontologyVersionIRI",
        "semanticRealizationId",
        "semanticSHA256",
        "dependencyCatalogSHA256",
        "levels",
        "subjectEntityIds",
    }
    require(
        isinstance(ext, dict) and set(ext) == fields,
        "MMIC-13",
        "invalid MMIC extension descriptor",
    )
    require(
        record.get("specificationVersion") == ext["profileVersion"] == VERSION
        and ext["ontologyVersionIRI"] == ONTOLOGY_VERSION,
        "CORE-01/MMIC-13",
        "profile, descriptor and ontology versions disagree",
    )
    levels = ext["levels"]
    require(
        isinstance(levels, list)
        and levels
        and len(set(levels)) == len(levels)
        and set(levels) <= set(LEVELS)
        and "documentation" in levels
        and ("comparison" not in levels or "decoding" in levels),
        "MMIC-12",
        "profile level declaration is invalid",
    )
    require(
        set(record["requiredCapabilities"]) == {CAPABILITIES[x] for x in levels},
        "MMIC-13",
        "profile capability declaration differs from its levels",
    )
    require(
        ext["dependencyCatalogSHA256"]
        == digest((resource_directory() / "dependencies.json").read_bytes()),
        "MMIC-13",
        "untrusted/stale dependency catalog",
    )
    assets = {r["id"]: r for r in manifest["realizations"]}
    require(
        ext["semanticRealizationId"] in assets
        and assets[ext["semanticRealizationId"]]["sha256"] == ext["semanticSHA256"]
        and assets[ext["semanticRealizationId"]]["mediaType"] == "application/json",
        "MMIC-13",
        "semantic sidecar pin differs from exact realization",
    )
    require(
        set(ext["subjectEntityIds"]) <= {x["id"] for x in manifest["entities"]}
        and bool(ext["subjectEntityIds"]),
        "MMIC-02",
        "MMIC subject does not resolve to core entity",
    )
    return ext


def check_resources():
    catalog = json.loads((resource_directory() / "dependencies.json").read_text())
    require(
        catalog["profile"] == PROFILE
        and catalog["specificationVersion"] == VERSION
        and catalog["networkResolution"] is False,
        "MMIC-13",
        "dependency catalog identity/policy mismatch",
    )
    for item in catalog["artifacts"]:
        path = resource_directory() / item["path"]
        require(
            path.is_file()
            and not path.is_symlink()
            and digest(path.read_bytes()) == item["sha256"],
            "MMIC-13",
            "local dependency artifact pin is stale",
        )


def validate_materialized(manifest, read_asset):
    report = {
        "profile": PROFILE,
        "specificationVersion": VERSION,
        "validator": "vao06/mmic",
        "status": "absent",
        "levels": {},
        "errors": [],
        "exercisedRequirements": [],
        "historicalCertification": "not established",
        "limits": {
            "assetBytes": MAX_BYTES,
            "jsonDepth": MAX_DEPTH,
            "records": MAX_RECORDS,
            "midiEvents": MAX_MIDI_EVENTS,
        },
        "networkResolution": False,
        "executesPackageCode": False,
    }
    try:
        ext = manifest_contract(manifest)
        if ext is None:
            return report
        check_resources()
        raw = read_asset(ext["semanticRealizationId"])
        if raw is None:
            report["status"] = "unmaterialized"
            return report
        require(
            digest(raw) == ext["semanticSHA256"],
            "MMIC-13",
            "semantic bytes differ from declared pin",
        )
        report["inputSHA256"] = digest(raw)
        data = strict_json(raw)
        validate_subjects(data, manifest)
        require(
            data.get("levels") == ext["levels"],
            "MMIC-12",
            "sidecar and descriptor levels disagree",
        )
        groups = {g["id"]: g for g in manifest["assetGroups"]}
        profile_record = next(
            r
            for k in ("profiles", "materializableProfiles")
            for r in manifest[k]
            if r["id"] == PROFILE
        )
        if "groupIds" in profile_record:
            closure, seen = set(), set()

            def add(gid):
                require(gid in groups, "MMIC-13", "profile group does not resolve")
                if gid in seen:
                    return
                seen.add(gid)
                closure.update(groups[gid]["realizationIds"])
                for dep in groups[gid]["dependsOnGroupIds"]:
                    add(dep)

            for gid in profile_record["groupIds"]:
                add(gid)
            require(
                ext["semanticRealizationId"] in closure,
                "MMIC-13",
                "profile group closure excludes semantic asset",
            )
            required_assets = asset_dependencies(data)
            require(
                required_assets <= closure,
                "MMIC-13",
                "profile group closure omits transitive capability inputs/outputs",
            )
        required = asset_dependencies(data)
        declared_assets = {r["id"] for r in manifest["realizations"]}
        require(
            required <= declared_assets,
            "MMIC-03",
            "domain artifact reference absent from core registry",
        )
        missing = [rid for rid in sorted(required) if read_asset(rid) is None]
        if missing:
            rights = {r["id"]: r for r in manifest["rights"]}
            restricted = {
                r["id"]
                for r in manifest["realizations"]
                if any(
                    rights[x]["access"] in ("restricted", "embargoed", "closed")
                    for x in r["rightsIds"]
                )
            }
            report["status"] = (
                "access-unavailable" if restricted & set(missing) else "unmaterialized"
            )
            report["missingRealizationIds"] = missing
            documentary = dict(
                data,
                levels=["documentation"],
                interpretations=[],
                comparisons=[],
                corrections=[],
                designs=data["designs"],
                fabrications=data["fabrications"],
            )
            validate_domain(
                documentary, manifest, read_asset, report["exercisedRequirements"]
            )
            report["levels"]["documentation"] = "valid"
            for level in data["levels"]:
                if level != "documentation":
                    report["levels"][level] = report["status"]
            return report
        validate_domain(data, manifest, read_asset, report["exercisedRequirements"])
        report["status"] = "valid"
        report["levels"] = {x: "valid" for x in data["levels"]}
        report["inputSHA256"] = ext["semanticSHA256"]
    except Unsupported as exc:
        report["status"] = "unsupported"
        report["errors"].append(str(exc))
    except (MMICError, KeyError, TypeError, ValueError, OSError) as exc:
        report["status"] = "invalid"
        report["errors"].append(str(exc))
    return report


def asset_dependencies(data):
    result = set()

    def walk(value):
        if isinstance(value, dict):
            for key, x in value.items():
                if key == "extensions":
                    continue
                if (
                    key.endswith("RealizationId") or key == "realizationId"
                ) and isinstance(x, str):
                    result.add(x)
                elif (
                    key.endswith("RealizationIds") or key == "realizationIds"
                ) and isinstance(x, list):
                    result.update(x)
                else:
                    walk(x)
        elif isinstance(value, list):
            for x in value:
                walk(x)

    walk(data)
    return result


def validate_isolated(manifest, read_asset, timeout=15):
    """Run only the distributed trusted validator under an explicit worker budget."""
    try:
        ext = manifest_contract(manifest)
        if ext is None:
            return validate_materialized(manifest, read_asset)
        cache = {}
        total = 0
        # Snapshot the selected dependency closure, never follow locators or execute source.
        semantic = read_asset(ext["semanticRealizationId"])
        required = {ext["semanticRealizationId"]}
        if semantic is not None:
            required.update(asset_dependencies(strict_json(semantic)))
        for rid in sorted(required):
            value = read_asset(rid)
            if isinstance(value, dict):
                cache[rid] = value
                continue
            if value is not None:
                require(
                    len(value) <= MAX_BYTES,
                    "MMIC-15",
                    "worker asset size budget exceeded",
                )
                total += len(value)
                require(
                    total <= 32 * 1024 * 1024,
                    "MMIC-15",
                    "worker snapshot exceeds 32 MiB",
                )
                cache[rid] = base64.b64encode(value).decode("ascii")
        request = json.dumps(
            {"manifest": manifest, "assets": cache}, allow_nan=False
        ).encode()
        require(
            len(request) <= 64 * 1024 * 1024, "MMIC-15", "worker request exceeds 64 MiB"
        )
        completed = subprocess.run(
            [sys.executable, "-I", str(Path(__file__).with_name("mmic_worker.py"))],
            input=request,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
        require(
            completed.returncode == 0 and len(completed.stdout) <= MAX_BYTES,
            "MMIC-15",
            "trusted worker failed or exceeded report budget",
        )
        return strict_json(completed.stdout)
    except Unsupported as exc:
        return {
            "profile": PROFILE,
            "status": "unsupported",
            "levels": {},
            "errors": [str(exc)],
        }
    except subprocess.TimeoutExpired:
        return {
            "profile": PROFILE,
            "status": "unsupported",
            "levels": {},
            "errors": ["MMIC-15: trusted worker exceeded 15-second time budget"],
        }
    except (OSError, MMICError, ValueError, KeyError, TypeError) as exc:
        return {
            "profile": PROFILE,
            "status": "invalid",
            "levels": {},
            "errors": [str(exc)],
        }
