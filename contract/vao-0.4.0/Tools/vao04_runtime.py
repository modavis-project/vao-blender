#!/usr/bin/env python3
"""Deterministic, declarative VAO 0.4.0 interaction reference interpreter."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

import rfc8785


MAX_REFERENCE_INPUT_EVENTS = 100_000
MAX_REFERENCE_TOTAL_MICROSTEPS = 100_000


def utf8_order(value: str) -> bytes:
    """Return the locale-independent string key required by VAO 0.4.0."""
    return value.encode("utf-8")


def canonical_bytes(value: Any) -> bytes:
    """Return RFC 8785 JSON Canonicalization Scheme bytes."""
    return rfc8785.dumps(value)


@dataclass
class PCG32:
    state: int
    increment: int

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> "PCG32":
        seed = int(record["seed"], 16) & ((1 << 64) - 1)
        stream = int(record["stream"], 16)
        generator = cls(0, ((stream << 1) | 1) & ((1 << 64) - 1))
        generator.next_uint32()
        generator.state = (generator.state + seed) & ((1 << 64) - 1)
        generator.next_uint32()
        return generator

    def next_uint32(self) -> int:
        old = self.state
        self.state = (old * 6364136223846793005 + self.increment) & ((1 << 64) - 1)
        xorshifted = (((old >> 18) ^ old) >> 27) & 0xFFFFFFFF
        rotation = (old >> 59) & 31
        return (
            (xorshifted >> rotation) | (xorshifted << ((-rotation) & 31))
        ) & 0xFFFFFFFF

    def uniform(self) -> float:
        return self.next_uint32() / 4294967296.0

    def next_word(self) -> tuple[int, int]:
        """Return a raw random word and its bit width for exact selection."""
        return self.next_uint32(), 32


@dataclass
class Xoshiro256StarStar:
    state: list[int]

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> "Xoshiro256StarStar":
        raw = bytes.fromhex(record["seed"])
        if len(raw) != 32:
            raise ValueError("xoshiro256** requires a 256-bit seed")
        words = [
            int.from_bytes(raw[index : index + 8], "big") for index in range(0, 32, 8)
        ]
        if not any(words):
            raise ValueError("xoshiro256** forbids the all-zero state")
        return cls(words)

    @staticmethod
    def _rotl(value: int, count: int) -> int:
        return ((value << count) | (value >> (64 - count))) & ((1 << 64) - 1)

    def next_uint64(self) -> int:
        s0, s1, s2, s3 = self.state
        result = (self._rotl((s1 * 5) & ((1 << 64) - 1), 7) * 9) & ((1 << 64) - 1)
        temporary = (s1 << 17) & ((1 << 64) - 1)
        s2 ^= s0
        s3 ^= s1
        s1 ^= s2
        s0 ^= s3
        s2 ^= temporary
        s3 = self._rotl(s3, 45)
        self.state = [s0, s1, s2, s3]
        return result

    def uniform(self) -> float:
        # The published generator authors recommend discarding the low 11 bits
        # before constructing a binary64 value in [0, 1).  Direct division of
        # a 64-bit word can round the maximum word to 1.0.
        return (self.next_uint64() >> 11) * (2.0**-53)

    def next_word(self) -> tuple[int, int]:
        """Return a raw random word and its bit width for exact selection."""
        return self.next_uint64(), 64


class RejectionSample(ValueError):
    """The word lies in the high tail that must be redrawn to avoid bias."""


def scaled_index(word: int, width: int, count: int) -> int:
    """Map an accepted unsigned word exactly uniformly to ``0..count-1``."""
    if count <= 0 or width <= 0 or count > (1 << width):
        raise ValueError("invalid exact-selection arguments")
    if not 0 <= word < (1 << width):
        raise ValueError("random word is outside its declared width")
    span = 1 << width
    limit = span - (span % count)
    if word >= limit:
        raise RejectionSample("random word is in the unbiased-selection tail")
    return word // (limit // count)


def categorical_index(word: int, width: int, weights: list[int]) -> int:
    """Select the first exact integer-weight interval hit by ``word``."""
    if not weights or any(
        isinstance(x, bool) or not isinstance(x, int) or x < 0 for x in weights
    ):
        raise ValueError("categorical weights must be non-negative integers")
    total = sum(weights)
    if total <= 0 or total > 9_007_199_254_740_991:
        raise ValueError("categorical weight total is outside 1..2^53-1")
    if width <= 0 or not 0 <= word < (1 << width):
        raise ValueError("random word is outside its declared width")
    if total > (1 << width):
        raise ValueError("categorical weight total exceeds the generator word range")
    span = 1 << width
    limit = span - (span % total)
    if word >= limit:
        raise RejectionSample("random word is in the unbiased-selection tail")
    ticket = word // (limit // total)
    cumulative = 0
    for index, weight in enumerate(weights):
        cumulative += weight
        if ticket < cumulative:
            return index
    raise AssertionError("exact categorical selection did not terminate")


def condition_matches(condition: dict[str, Any], state: dict[str, Any]) -> bool:
    actual = state.get(condition["stateVariableId"])
    expected = condition.get("value")
    operation = condition["operator"]
    if operation == "equals":
        return actual == expected
    if operation == "not-equals":
        return actual != expected
    if operation == "less-than":
        return actual is not None and actual < expected
    if operation == "less-than-or-equal":
        return actual is not None and actual <= expected
    if operation == "greater-than":
        return actual is not None and actual > expected
    if operation == "greater-than-or-equal":
        return actual is not None and actual >= expected
    return False


class RuntimeError04(ValueError):
    pass


class Interpreter:
    def __init__(self, manifest: dict[str, Any]):
        self.manifest = manifest
        self.model = manifest.get("interactionModel") or {}
        self.runtime = manifest["runtime"]
        self.semantics = self.runtime["executionSemantics"]
        self.events = {x["id"]: x for x in self.model.get("eventTypes", [])}
        self.states = {x["id"]: x for x in self.model.get("stateVariables", [])}
        self.transitions = sorted(
            self.model.get("transitions", []),
            key=lambda x: (-x.get("priority", 0), utf8_order(x["id"])),
        )
        self.transitions_by_event: dict[str, list[dict[str, Any]]] = {}
        for transition in self.transitions:
            self.transitions_by_event.setdefault(transition["eventTypeId"], []).append(
                transition
            )
        self.processes = {x["id"]: x for x in self.model.get("processModels", [])}
        self.routes = {x["id"]: x for x in self.model.get("routingRules", [])}
        self.renders = self.model.get("renderBindings", [])
        random_records = {x["id"]: x for x in self.runtime.get("randomSources", [])}
        random_records.update({x["id"]: x for x in self.model.get("randomSources", [])})
        self.random = {
            key: (
                PCG32.from_record(value)
                if value["algorithm"] == "pcg32"
                else Xoshiro256StarStar.from_record(value)
            )
            for key, value in random_records.items()
        }
        self.maximum_microsteps = self.semantics.get("maximumMicrosteps", 10_000)
        self._microsteps = 0
        self._total_microsteps = 0

    def _consume_microstep(self) -> None:
        self._microsteps += 1
        self._total_microsteps += 1
        if self._microsteps > self.maximum_microsteps:
            raise RuntimeError04("maximumMicrosteps exceeded")
        if self._total_microsteps > MAX_REFERENCE_TOTAL_MICROSTEPS:
            raise RuntimeError04(
                "reference total trace-microstep safety limit exceeded"
            )

    def initial_state(self, override: dict[str, Any] | None = None) -> dict[str, Any]:
        state = {
            record["id"]: record["defaultValue"]
            for record in self.model.get("stateVariables", [])
        }
        state.update(override or {})
        return state

    def _valid_state_value(self, identifier: str, value: Any) -> bool:
        record = self.states[identifier]
        kind = record["valueType"]
        if kind == "boolean":
            valid = isinstance(value, bool)
        elif kind == "integer":
            valid = isinstance(value, int) and not isinstance(value, bool)
        elif kind == "number":
            valid = isinstance(value, (int, float)) and not isinstance(value, bool)
        else:
            valid = value in record.get("allowedValues", [])
        if not valid:
            return False
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if (
                record.get("minimumValue") is not None
                and value < record["minimumValue"]
            ):
                return False
            if (
                record.get("maximumValue") is not None
                and value > record["maximumValue"]
            ):
                return False
        return True

    def _stochastic_candidate_index(
        self, process: dict[str, Any], candidate_count: int
    ) -> int:
        generator = self.random.get(process.get("randomSourceId"))
        if generator is None:
            raise RuntimeError04(
                f"Missing reproducible random source for {process['id']}"
            )
        if candidate_count < 1:
            raise RuntimeError04(
                f"Stochastic process {process['id']} has no selectable candidates"
            )
        distribution = process["probabilityDistribution"]
        weights = (
            [
                distribution["parameters"].get(str(index), 0)
                for index in range(candidate_count)
            ]
            if distribution["kind"] == "categorical"
            else None
        )
        while True:
            self._consume_microstep()
            word, width = generator.next_word()
            try:
                return (
                    categorical_index(word, width, weights)
                    if weights is not None
                    else scaled_index(word, width, candidate_count)
                )
            except RejectionSample:
                continue
            except ValueError as exc:
                raise RuntimeError04(
                    f"Invalid {distribution['kind']} distribution for "
                    f"{process['id']}: {exc}"
                ) from exc

    def _process_actions(
        self, process: dict[str, Any]
    ) -> list[tuple[str, dict[str, Any]]]:
        """Expand one Process iteratively under the normative candidate ordering."""
        result: list[tuple[str, dict[str, Any]]] = []
        active: set[str] = set()
        work: list[tuple[Any, ...]] = [("enter", process)]
        while work:
            operation, *arguments = work.pop()
            if operation == "exit":
                active.remove(arguments[0])
                continue
            if operation == "action":
                process_id, action = arguments
                if action.get("delayConstraintId") is not None:
                    raise RuntimeError04(
                        "Offline conformance traces do not admit delayed process actions"
                    )
                self._consume_microstep()
                result.append((process_id, action))
                continue
            if operation == "actions":
                current, index = arguments
                actions = current.get("actions", [])
                if index < len(actions):
                    work.append(("actions", current, index + 1))
                    work.append(("action", current["id"], actions[index]))
                else:
                    work.append(("children", current, 0))
                continue
            if operation == "children":
                current, index = arguments
                children = current.get("childProcessIds", [])
                if index < len(children):
                    child = children[index]
                    if child not in self.processes:
                        raise RuntimeError04(f"Unknown child process {child}")
                    work.append(("children", current, index + 1))
                    work.append(("enter", self.processes[child]))
                else:
                    work.append(("exit", current["id"]))
                continue

            current = arguments[0]
            identifier = current["id"]
            if identifier in active:
                raise RuntimeError04(f"Process graph cycle at {identifier}")
            if current.get("terminationPolicy") != "completed" or current.get(
                "timingConstraintIds"
            ):
                raise RuntimeError04(
                    "Offline conformance traces admit only immediately completed, "
                    f"unscheduled processes ({identifier})"
                )
            if current.get("processKind") not in {
                "one-shot",
                "compound",
                "stochastic",
            }:
                raise RuntimeError04(
                    "Offline conformance traces do not model lifecycle process kind "
                    f"{current.get('processKind')!r} ({identifier})"
                )
            active.add(identifier)
            if current["processKind"] != "stochastic":
                work.append(("actions", current, 0))
                continue

            actions = current.get("actions", [])
            children = current.get("childProcessIds", [])
            selected = self._stochastic_candidate_index(
                current, len(actions) + len(children)
            )
            work.append(("exit", identifier))
            if selected < len(actions):
                work.append(("action", identifier, actions[selected]))
            else:
                child = children[selected - len(actions)]
                if child not in self.processes:
                    raise RuntimeError04(f"Unknown child process {child}")
                work.append(("enter", self.processes[child]))
        return result

    def execute(
        self, events: list[dict[str, Any]], initial_state: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        self._microsteps = 0
        self._total_microsteps = 0
        if len(events) > MAX_REFERENCE_INPUT_EVENTS:
            raise RuntimeError04("reference input-event safety limit exceeded")
        state = self.initial_state(initial_state)
        emitted: list[dict[str, Any]] = []
        selected: list[str] = []
        ordered = sorted(
            events,
            key=lambda event: (
                event["timestamp"],
                -event.get("priority", 0),
                utf8_order(event["eventTypeId"]),
                event["sequence"],
            ),
        )
        for event in ordered:
            # maximumMicrosteps bounds one run-to-completion cycle.  A long
            # finite trace must not exhaust a process-global lifetime budget.
            self._microsteps = 0
            snapshot = dict(state)
            matching = [
                transition
                for transition in self.transitions_by_event.get(
                    event["eventTypeId"], []
                )
                if transition["eventTypeId"] == event["eventTypeId"]
                and (
                    transition.get("controlId") is None
                    or transition.get("controlId") == event.get("controlId")
                )
                and all(
                    condition_matches(c, snapshot)
                    for c in transition.get("conditions", [])
                )
            ]
            writes: dict[str, tuple[Any, set[str], int]] = {}
            actions: list[tuple[str, int, int, dict[str, Any], dict[str, Any]]] = []
            for transition_rank, transition in enumerate(matching):
                for index, action in enumerate(transition["actions"]):
                    actions.append(
                        (
                            action.get("executionGroup", ""),
                            transition_rank,
                            index,
                            action,
                            transition,
                        )
                    )
            for _, transition_rank, _, action, transition in sorted(
                actions, key=lambda item: (utf8_order(item[0]), item[1], item[2])
            ):
                self._consume_microstep()
                operation, target = action["operation"], action["targetId"]
                if action.get("delayConstraintId") is not None:
                    raise RuntimeError04(
                        "Offline conformance traces do not admit delayed actions"
                    )
                if operation in {"set-state", "toggle-state", "increment-state"}:
                    current = writes.get(target, (snapshot.get(target), set(), -1))[0]
                    value = action.get("value")
                    if operation == "toggle-state":
                        if not isinstance(current, bool):
                            raise RuntimeError04(
                                f"toggle-state target {target} is not boolean"
                            )
                        value = not current
                    if operation == "increment-state":
                        if (
                            isinstance(current, bool)
                            or not isinstance(current, (int, float))
                            or isinstance(value, bool)
                            or not isinstance(value, (int, float))
                        ):
                            raise RuntimeError04(
                                f"increment-state target/value for {target} is not numeric"
                            )
                        value = current + value
                    previous = writes.get(target)
                    policy = transition["conflictPolicy"]
                    if previous is not None and previous[0] != value:
                        policies = previous[1] | {policy}
                        if len(policies) != 1:
                            raise RuntimeError04(
                                f"Conflicting write policies disagree for {target}"
                            )
                        resolved_policy = next(iter(policies))
                        if resolved_policy in {"reject", "merge-disjoint"}:
                            raise RuntimeError04(
                                f"Rejected conflicting write to {target}"
                            )
                        if (
                            resolved_policy == "priority"
                            and transition_rank > previous[2]
                        ):
                            continue
                    if not self._valid_state_value(target, value):
                        raise RuntimeError04(
                            f"State write to {target} violates its declared domain"
                        )
                    if previous is not None:
                        writes[target] = (
                            value,
                            previous[1] | {policy},
                            min(previous[2], transition_rank),
                        )
                    else:
                        writes[target] = (value, {policy}, transition_rank)
                elif operation == "emit-event":
                    emitted.append(
                        {
                            "eventTypeId": target,
                            "timestamp": event["timestamp"],
                            "sourceTransitionId": transition["id"],
                        }
                    )
                elif operation == "route-event":
                    emitted.append(
                        {
                            "routeId": target,
                            "timestamp": event["timestamp"],
                            "sourceTransitionId": transition["id"],
                        }
                    )
                elif operation == "start-process":
                    for process_id, process_action in self._process_actions(
                        self.processes[target]
                    ):
                        process_event = {
                            "processId": process_id,
                            "operation": process_action["operation"],
                            "targetId": process_action["targetId"],
                            "timestamp": event["timestamp"],
                            "sourceTransitionId": transition["id"],
                        }
                        for field in ("value", "keyOffset"):
                            if field in process_action:
                                process_event[field] = process_action[field]
                        emitted.append(process_event)
                elif operation == "stop-process":
                    emitted.append(
                        {
                            "processId": target,
                            "operation": "stop-process",
                            "timestamp": event["timestamp"],
                            "sourceTransitionId": transition["id"],
                        }
                    )
                elif operation == "select-render-binding":
                    selected.append(target)
                else:
                    raise RuntimeError04(
                        f"Unsupported declarative operation {operation}"
                    )
            state.update({key: value[0] for key, value in writes.items()})
            for binding in self.renders:
                if binding.get("eventTypeId") not in (None, event["eventTypeId"]):
                    continue
                if all(
                    condition_matches(c, state) for c in binding.get("conditions", [])
                ):
                    selected.append(binding["id"])
        result = {
            "state": state,
            "emittedEvents": emitted,
            "renderBindingIds": list(dict.fromkeys(selected)),
        }
        return result


def trace_digest(
    initial_state: dict[str, Any],
    input_events: list[dict[str, Any]],
    expected: dict[str, Any],
) -> str:
    return hashlib.sha256(
        canonical_bytes(
            {
                "initialState": initial_state,
                "inputEvents": input_events,
                "expected": expected,
            }
        )
    ).hexdigest()


def verify_trace(manifest: dict[str, Any], trace: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    try:
        expected_digest = trace_digest(
            trace.get("initialState", {}), trace["inputEvents"], trace["expected"]
        )
    except (rfc8785.CanonicalizationError, KeyError, TypeError, ValueError) as exc:
        return [
            f"Conformance trace {trace.get('id', '<unknown>')} cannot be canonicalized with RFC 8785: {exc}."
        ]
    digest = trace["digest"]
    if digest["algorithm"] != "sha256" or digest["value"] != expected_digest:
        errors.append(f"Conformance trace {trace['id']} has a non-canonical digest.")
    try:
        actual = Interpreter(manifest).execute(
            trace["inputEvents"], trace.get("initialState")
        )
    except (KeyError, TypeError, ValueError, RuntimeError04) as exc:
        errors.append(f"Conformance trace {trace['id']} cannot execute: {exc}")
        return errors
    if actual != trace["expected"]:
        errors.append(
            f"Conformance trace {trace['id']} does not match deterministic execution."
        )
    return errors
