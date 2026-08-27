#!/usr/bin/env python3
"""Build the complete Cuntz Positiv VAO 0.2.2 workspace from audited sources."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
import uuid
from pathlib import Path
from typing import Any

FORMAT_VERSION = "0.2.2"
CREATED_AT = "2026-08-24T12:00:00Z"
MIMETYPE = "application/vnd.modavis.vao+zip"
SCHEMA = "https://w3id.org/modavis/vao/0.2/schema/manifest.json"
CONTEXT = "https://w3id.org/modavis/vao/0.2/context.jsonld"
VAO = "https://w3id.org/modavis/vao/ontology#"
VAOV = "https://w3id.org/modavis/vao/vocab/"
MODAUDIO = "https://w3id.org/modavis/ontology/audio#"
MODINST = "https://w3id.org/modavis/ontology/instrument#"
QUDT_M = "http://qudt.org/vocab/unit/M"
CORE = "https://w3id.org/modavis/vao/profile/core/0.2"
RESEARCH = "https://w3id.org/modavis/vao/profile/research/0.2"
PLAYABLE = "https://w3id.org/modavis/vao/profile/playable/0.2"
SPATIAL = "https://w3id.org/modavis/vao/profile/spatial/0.2"
EXPERIENTIAL = "https://w3id.org/modavis/vao/profile/experiential/0.2"
PROJECT = "https://example.org/vao-blender/cuntz#"
NAMESPACE = uuid.UUID("1f77bdd6-ff7a-4b1a-a50e-6ad0fa5b2002")

RAW_AUDIO = Path("/Volumes/UkolovMac/IADs/RAW/PositivXR")
UNITY = Path(
    "/Volumes/UkolovXfer/Ukolov_Transfer_2026-08-11/Applications/Cuntz_Positiv_Unity_AR_VAOrgan/VAOrgan"
)
ORGREC = Path("/Users/dominik/Desktop/Projects/orgrec")
PROJECT_ROOT = Path("/Users/dominik/Desktop/Projects/vao-blender")

KEYS = [
    36,
    38,
    40,
    41,
    43,
    45,
    46,
    47,
    48,
    49,
    50,
    51,
    52,
    53,
    54,
    55,
    56,
    57,
    58,
    59,
    60,
    61,
    62,
    63,
    64,
    65,
    66,
    67,
    68,
    69,
    70,
    71,
    72,
    73,
    74,
    75,
    76,
    77,
    78,
    79,
    80,
    81,
    82,
    83,
    84,
]
STOPS = {
    "ged": {"label": "Gedackt 8′", "offset": 0},
    "princ4": {"label": "Principal 4′", "offset": 12},
    "princ2": {"label": "Principal 2′", "offset": 24},
    "qui223": {"label": "Quint 2 2/3′", "offset": 19},
    "reg8": {"label": "Regal 8′", "offset": 0},
}


def identifier(kind: str, key: str) -> str:
    return f"urn:uuid:{uuid.uuid5(NAMESPACE, f'{kind}:{key}')}"


PACKAGE_ID = identifier("package", "cuntz-positiv-4010243-vao-0.2.2")


def asset_id(path: str) -> str:
    return "urn:vao:asset:" + hashlib.sha256(path.encode("utf-8")).hexdigest()


def relation_id(subject: str, predicate: str, obj: str) -> str:
    return identifier("relation", f"{subject}|{predicate}|{obj}")


def sha256_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def media_type(path: Path) -> str:
    suffix = path.suffix.lower()
    return {
        ".wav": "audio/wav",
        ".mp3": "audio/mpeg",
        ".glb": "model/gltf-binary",
        ".json": "application/json",
        ".md": "text/markdown",
        ".txt": "text/plain",
        ".cs": "text/plain",
        ".meta": "text/yaml",
        ".unity": "text/yaml",
        ".anim": "text/yaml",
        ".controller": "text/yaml",
        ".mat": "text/yaml",
        ".asset": "text/yaml",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".fbx": "application/octet-stream",
        ".bak": "application/octet-stream",
    }.get(suffix, "application/octet-stream")


def entity(
    entity_id: str, kind: str, label: str, type_iri: str, properties: dict[str, Any] | None = None
) -> dict[str, Any]:
    return {
        "id": entity_id,
        "kind": kind,
        "types": [type_iri],
        "labels": {"en": label},
        "properties": properties or {},
    }


def relation(subject: str, predicate: str, obj: str, status: str = "asserted") -> dict[str, Any]:
    return {
        "id": relation_id(subject, predicate, obj),
        "subjectId": subject,
        "predicate": predicate,
        "objectId": obj,
        "status": status,
    }


def interaction_properties(
    interaction_type: str, binding: str, domain: dict[str, Any], timing: dict[str, Any]
) -> dict[str, Any]:
    return {
        VAO + "interactionType": VAOV + "interaction/" + interaction_type,
        VAO + "controlProtocol": {"binding": binding, "noteDomain": "MIDI-1.0-note-number"},
        VAO + "controlDomain": domain,
        VAO + "timingPolicy": timing,
    }


def copy_file(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and destination.stat().st_size == source.stat().st_size:
        return
    shutil.copy2(source, destination)


def copy_or_link(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        destination.unlink()
    try:
        os.link(source, destination)
    except OSError:
        shutil.copy2(source, destination)


def add_asset_spec(
    specs: dict[str, dict[str, Any]],
    path: str,
    *,
    roles: list[str],
    representation: str,
    about: list[str],
    original: str | None = None,
    properties: dict[str, Any] | None = None,
) -> None:
    specs[path] = {
        "roles": roles,
        "representationStatus": representation,
        "aboutEntityIds": about,
        "originalFilename": original,
        "properties": properties or {},
    }


def collect_files(root: Path) -> list[Path]:
    return sorted(
        path
        for path in root.rglob("*")
        if path.is_file() and not path.name.startswith("._") and path.name != ".DS_Store"
    )


def build(workspace: Path) -> None:
    workspace.mkdir(parents=True, exist_ok=True)
    payload = workspace / "payload"
    payload.mkdir(parents=True, exist_ok=True)
    (workspace / "mimetype").write_bytes(MIMETYPE.encode("ascii"))

    inspection_path = ORGREC / "Artifacts/PositivXR/inspection.json"
    inspection = json.loads(inspection_path.read_text(encoding="utf-8"))
    inspection_by_key = {(item["stopCode"], item["midiNote"]): item for item in inspection["files"]}
    conversion = json.loads(
        (PROJECT_ROOT / "build/model-conversion-report.json").read_text(encoding="utf-8")
    )
    conversion_by_name = {Path(item["source"]).name: item for item in conversion["models"]}

    instrument_id = identifier("instrument", "4010243-cuntz-positiv")
    keyboard_id = identifier("component", "keyboard")
    experience_id = identifier("experience", "generic-model-viewing")
    entities: list[dict[str, Any]] = [
        entity(
            instrument_id,
            "instrument",
            "Cuntz Positiv 4010243",
            MODINST + "MusicalInstrument",
            {
                PROJECT + "sourceRecordIdentifier": "4010243",
                PROJECT + "observedCompass": KEYS,
                PROJECT + "missingShortOctaveKeys": [37, 39, 42, 44],
                PROJECT
                + "identityStatus": "Source-bound identifier; canonical historical identity not asserted.",
            },
        ),
        entity(keyboard_id, "component", "Keyboard", MODINST + "InstrumentComponent"),
        entity(
            experience_id,
            "experience",
            "Blender-ready generic model view",
            VAO + "Experience",
            {VAO + "experienceCapability": VAOV + "capability/generic-model-viewing"},
        ),
    ]
    relations: list[dict[str, Any]] = [
        relation(instrument_id, MODINST + "hasComponent", keyboard_id, "accepted")
    ]

    key_ids: dict[int, str] = {}
    key_interaction_ids: dict[int, str] = {}
    for key in KEYS:
        component_id = identifier("component", f"key-{key}")
        interaction_id = identifier("interaction", f"key-{key}")
        key_ids[key] = component_id
        key_interaction_ids[key] = interaction_id
        entities.append(
            entity(
                component_id,
                "component",
                f"Key {key}",
                MODINST + "InstrumentComponent",
                {MODAUDIO + "keyNumber": key},
            )
        )
        entities.append(
            entity(
                interaction_id,
                "interaction",
                f"Gate key {key}",
                VAO + "Interaction",
                interaction_properties(
                    "excite",
                    "host-note-gate",
                    {"minimum": 0.0, "maximum": 1.0, "unit": "normalized", "keyNumber": key},
                    {"attack": "immediate", "release": "on-gate-close"},
                ),
            )
        )
        relations.extend(
            [
                relation(keyboard_id, MODINST + "hasComponent", component_id, "accepted"),
                relation(interaction_id, VAO + "activates", component_id, "accepted"),
            ]
        )

    stop_ids: dict[str, str] = {}
    configuration_ids: dict[str, str] = {}
    for code, metadata in STOPS.items():
        stop_id = identifier("component", f"stop-{code}")
        configuration_id = identifier("configuration", f"stop-{code}-enabled")
        stop_interaction_id = identifier("interaction", f"stop-{code}-toggle")
        stop_ids[code] = stop_id
        configuration_ids[code] = configuration_id
        entities.extend(
            [
                entity(
                    stop_id,
                    "component",
                    str(metadata["label"]),
                    MODINST + "InstrumentComponent",
                    {
                        PROJECT + "sourceCode": code,
                        PROJECT + "nominalPitchOffsetSemitones": metadata["offset"],
                        PROJECT
                        + "offsetStatus": "Editorial stop-name interpretation; not a measured tuning claim.",
                    },
                ),
                entity(
                    configuration_id,
                    "configuration",
                    f"{metadata['label']} enabled",
                    MODINST + "InstrumentConfiguration",
                    {
                        PROJECT + "selectionPolicy": "independent-toggle",
                    },
                ),
                entity(
                    stop_interaction_id,
                    "interaction",
                    f"Toggle {metadata['label']}",
                    VAO + "Interaction",
                    interaction_properties(
                        "select",
                        "host-toggle",
                        {"minimum": 0, "maximum": 1, "unit": "boolean"},
                        {"selection": "toggle", "exclusivity": "independent"},
                    ),
                ),
            ]
        )
        relations.extend(
            [
                relation(instrument_id, MODINST + "hasComponent", stop_id, "accepted"),
                relation(instrument_id, VAO + "offersConfiguration", configuration_id, "accepted"),
                relation(stop_interaction_id, VAO + "configuration", configuration_id, "accepted"),
                relation(stop_interaction_id, VAO + "activates", stop_id, "accepted"),
            ]
        )

    specs: dict[str, dict[str, Any]] = {}
    source_inventory: list[dict[str, Any]] = []
    sample_asset_ids: dict[tuple[str, int], str] = {}
    parameter_ids: dict[tuple[str, int], str] = {}
    voice_ids: dict[tuple[str, int], str] = {}
    sounding_ids: dict[tuple[str, int], str] = {}

    for code, metadata in STOPS.items():
        for key in KEYS:
            observed = inspection_by_key[(code, key)]
            filename = observed["filename"]
            source = RAW_AUDIO / filename
            if not source.is_file():
                raise FileNotFoundError(source)
            destination_path = f"payload/audio/samples/{code}/{filename}"
            copy_file(source, workspace / destination_path)
            sample_id = asset_id(destination_path)
            sample_asset_ids[(code, key)] = sample_id
            sounding_id = identifier("component", f"sounding-position-{code}-{key}")
            parameter_id = identifier("parameter-set", f"sample-playback-{code}-{key}")
            voice_id = identifier("interaction", f"voice-{code}-{key}")
            sounding_ids[(code, key)] = sounding_id
            parameter_ids[(code, key)] = parameter_id
            voice_ids[(code, key)] = voice_id
            target_key = key + int(metadata["offset"])
            target_frequency = 440.0 * math.pow(2.0, (target_key - 69) / 12.0)
            entities.extend(
                [
                    entity(
                        sounding_id,
                        "component",
                        f"{metadata['label']} sounding position, key {key}",
                        MODINST + "InstrumentComponent",
                        {
                            MODAUDIO + "keyNumber": key,
                            PROJECT + "stopCode": code,
                        },
                    ),
                    entity(
                        parameter_id,
                        "parameterSet",
                        f"Playback parameters: {metadata['label']}, key {key}",
                        MODAUDIO + "SamplePlaybackParameters",
                        {
                            MODAUDIO + "rootKeyNumber": key,
                            MODAUDIO + "minimumKeyNumber": key,
                            MODAUDIO + "maximumKeyNumber": key,
                            MODAUDIO + "minimumVelocity": 1,
                            MODAUDIO + "maximumVelocity": 127,
                            MODAUDIO + "targetFrequencyHz": target_frequency,
                            MODAUDIO + "gainDB": 0.0,
                            MODAUDIO + "pitchTrackingMode": "preserveRecordedPitch",
                            MODAUDIO + "envelope": {
                                "attackSeconds": 0.0,
                                "releaseSeconds": 0.3,
                                "sustainLevel": 1.0,
                                "curve": "linear",
                            },
                            MODAUDIO + "status": "reviewed",
                            MODAUDIO + "channelPolicy": "stereo-preserve",
                            MODAUDIO + "noteOffPolicy": "voice-scoped-fade",
                            PROJECT
                            + "targetFrequencyBasis": "12-TET A4=440 interpretation of stop name; recorded pitch is preserved and no measured source tuning is asserted.",
                        },
                    ),
                    entity(
                        voice_id,
                        "interaction",
                        f"Sound {metadata['label']}, key {key}",
                        VAO + "Interaction",
                        interaction_properties(
                            "excite",
                            "internal-scoped-voice",
                            {
                                "minimum": 0.0,
                                "maximum": 1.0,
                                "unit": "normalized",
                                "keyNumber": key,
                                "configurationId": configuration_ids[code],
                            },
                            {
                                "attack": "immediate",
                                "release": "voice-scoped-0.3-second-linear-fade",
                            },
                        ),
                    ),
                ]
            )
            relations.extend(
                [
                    relation(stop_ids[code], MODINST + "hasComponent", sounding_id, "accepted"),
                    relation(voice_id, VAO + "triggeredBy", key_interaction_ids[key], "accepted"),
                    relation(voice_id, VAO + "configuration", configuration_ids[code], "accepted"),
                    relation(voice_id, VAO + "activates", sounding_id, "accepted"),
                    relation(voice_id, VAO + "usesSample", sample_id, "accepted"),
                    relation(
                        voice_id, MODAUDIO + "usesPlaybackParameters", parameter_id, "accepted"
                    ),
                    relation(sounding_id, VAO + "hasRepresentation", sample_id, "accepted"),
                ]
            )
            add_asset_spec(
                specs,
                destination_path,
                roles=[VAOV + "asset-role/audio-master"],
                representation=VAOV + "representation-status/captured",
                about=[instrument_id, stop_ids[code], sounding_id, key_ids[key]],
                original=filename,
                properties={
                    MODAUDIO + "sampleRate": observed["sampleRate"],
                    MODAUDIO + "channelCount": observed["channelCount"],
                    MODAUDIO + "frameCount": observed["frameCount"],
                    MODAUDIO + "durationSeconds": observed["durationSeconds"],
                    MODAUDIO + "encoding": observed["formatDescription"],
                    PROJECT + "variant": observed.get(
                        "variant", "source filename has no explicit variant suffix"
                    ),
                },
            )
            source_inventory.append(
                {
                    "source": str(source),
                    "payloadPath": destination_path,
                    "category": "authoritative isolated WAVE master",
                }
            )

    # Source evidence retained from the Unity application without duplicated Resources/Audio samples.
    unity_groups = [
        "Assets/Models",
        "Assets/Scripts",
        "Assets/Scenes",
        "Assets/Animations",
        "Assets/Audio",
        "Assets/Images",
        "Assets/Marker",
    ]
    for group in unity_groups:
        root = UNITY / group
        for source in collect_files(root):
            relative = source.relative_to(UNITY).as_posix()
            destination_path = "payload/source/unity/" + relative
            copy_file(source, workspace / destination_path)
            roles = [VAOV + "asset-role/source-evidence"]
            if source.suffix.lower() == ".mp3":
                roles.append(VAOV + "asset-role/performance-media")
            if source.suffix.lower() in {".anim", ".controller"}:
                roles.append(VAOV + "asset-role/animation")
            add_asset_spec(
                specs,
                destination_path,
                roles=roles,
                representation=VAOV + "representation-status/authored",
                about=[instrument_id],
                original=source.name,
            )
            source_inventory.append(
                {
                    "source": str(source),
                    "payloadPath": destination_path,
                    "category": "Unity source evidence",
                }
            )

    root_unity_names = [
        "4010243_M1.anim",
        "4010243_M1.anim.bak",
        "4010243_M1.anim.bak.meta",
        "4010243_M1.anim.meta",
        "New Animation 1.anim",
        "New Animation 1.anim.meta",
        "New Animation.anim",
        "New Animation.anim.meta",
        "New Animator Controller.controller",
        "New Animator Controller.controller.meta",
        "output.anim",
        "output.anim.meta",
        "positiv_keys.fbx",
        "positiv_keys.fbx.meta",
        "Material.002.mat",
        "Material.002.mat.meta",
    ]
    for name in root_unity_names:
        source = UNITY / "Assets" / name
        if not source.is_file():
            continue
        destination_path = "payload/source/unity/Assets/" + name
        copy_file(source, workspace / destination_path)
        roles = [VAOV + "asset-role/source-evidence"]
        if source.suffix.lower() in {".anim", ".controller"}:
            roles.append(VAOV + "asset-role/animation")
        add_asset_spec(
            specs,
            destination_path,
            roles=roles,
            representation=VAOV + "representation-status/authored",
            about=[instrument_id],
            original=source.name,
        )
        source_inventory.append(
            {
                "source": str(source),
                "payloadPath": destination_path,
                "category": "Unity root source evidence",
            }
        )

    for relative in [
        "ProjectSettings/ProjectVersion.txt",
        "ProjectSettings/EditorBuildSettings.asset",
        "Packages/manifest.json",
        "Packages/packages-lock.json",
    ]:
        source = UNITY / relative
        if source.is_file():
            destination_path = "payload/source/unity/" + relative
            copy_file(source, workspace / destination_path)
            add_asset_spec(
                specs,
                destination_path,
                roles=[VAOV + "asset-role/source-evidence"],
                representation=VAOV + "representation-status/authored",
                about=[instrument_id],
                original=source.name,
            )
            source_inventory.append(
                {
                    "source": str(source),
                    "payloadPath": destination_path,
                    "category": "Unity project metadata",
                }
            )

    analysis_assets: list[str] = []
    for name in ["inspection.json", "TIMBRE_VALIDATION_0.2.0.json", "ANALYSIS_RESULTS.md"]:
        source = ORGREC / "Artifacts/PositivXR" / name
        destination_path = "payload/evidence/orgrec/" + name
        copy_file(source, workspace / destination_path)
        add_asset_spec(
            specs,
            destination_path,
            roles=[VAOV + "asset-role/source-evidence", VAOV + "asset-role/analysis-result"],
            representation=VAOV + "representation-status/authored",
            about=[instrument_id],
            original=name,
        )
        analysis_assets.append(asset_id(destination_path))
        source_inventory.append(
            {
                "source": str(source),
                "payloadPath": destination_path,
                "category": "OrgRec inspection/analysis evidence",
            }
        )

    model_source_paths: dict[str, str] = {}
    for model_name in ["4010243_segmented.fbx", "4010243_segmented_03b2.fbx"]:
        model_source_paths[model_name] = "payload/source/unity/Assets/Models/" + model_name
    model_source_paths["positiv_keys.fbx"] = "payload/source/unity/Assets/positiv_keys.fbx"

    model_assets: dict[str, str] = {}
    model_roles = [VAOV + "asset-role/three-dimensional-model", VAOV + "asset-role/spatial-model"]
    for model_name in ["4010243_segmented.fbx", "4010243_segmented_03b2.fbx", "positiv_keys.fbx"]:
        stem = Path(model_name).stem
        source = PROJECT_ROOT / "build/model-derivatives" / f"{stem}.glb"
        destination_path = f"payload/models/{stem}.glb"
        copy_or_link(source, workspace / destination_path)
        report = conversion_by_name[model_name]
        dimensions = report["bounds"]["dimensionsXYZ"]
        about = (
            [instrument_id] if model_name != "positiv_keys.fbx" else [instrument_id, keyboard_id]
        )
        add_asset_spec(
            specs,
            destination_path,
            roles=model_roles,
            representation=VAOV + "representation-status/processed",
            about=about,
            original=f"{stem}.glb",
            properties={
                VAO
                + "coordinateSystem": "Blender glTF 2.0 local model frame; source scale is unverified",
                VAO + "coordinateUnit": QUDT_M,
                VAO + "handedness": "right",
                VAO + "upAxis": "Y",
                VAO + "physicalDimensions": {
                    "width": dimensions[0],
                    "height": dimensions[2],
                    "depth": dimensions[1],
                    "unit": QUDT_M,
                },
                PROJECT
                + "scaleStatus": "Nominal imported FBX units represented as glTF metres; not verified against physical survey.",
                PROJECT + "sourceFBXAssetId": asset_id(model_source_paths[model_name]),
            },
        )
        model_assets[model_name] = asset_id(destination_path)
        source_inventory.append(
            {
                "source": str(source),
                "payloadPath": destination_path,
                "category": "Blender 5.1.1 glTF derivative",
            }
        )

    conversion_report_destination = "payload/evidence/model-conversion-report.json"
    copy_file(
        PROJECT_ROOT / "build/model-conversion-report.json",
        workspace / conversion_report_destination,
    )
    add_asset_spec(
        specs,
        conversion_report_destination,
        roles=[VAOV + "asset-role/source-evidence", VAOV + "asset-role/analysis-result"],
        representation=VAOV + "representation-status/authored",
        about=[instrument_id],
    )
    analysis_assets.append(asset_id(conversion_report_destination))

    contract_pin = {
        "vaoVersion": FORMAT_VERSION,
        "status": "private-development release candidate; no newer public release found on 2026-08-24",
        "releaseBundle": str(ORGREC / "dist/vao-specification-0.2.2-rc.zip"),
        "releaseBundleSHA256": "76b55f33b09c94ad90aac79e8a599d007841e2c11288664f9c67987b4e68f328",
        "schemaSHA256": "c7a2cde4a68edca0a87068abfff88325a791b6c06fbe5d9025115046e27f7c3b",
        "contextSHA256": "781122be3f9c098b42f0ee045c8f11d8eda120a1561224b049e6ca1b43d052bb",
        "vocabularySHA256": "71ad36568b2e805eef79af39b7bc08dcfd8a19d2032e48b59b18dbb940bc627b",
        "standardDocumentSHA256": "ac73a1988c119d99f8e0be421f19e402bf0a70b00a6e024bfafa526d030ccf56",
    }
    contract_path = "payload/documentation/VAO_CONTRACT_PIN.json"
    (workspace / contract_path).parent.mkdir(parents=True, exist_ok=True)
    (workspace / contract_path).write_text(
        json.dumps(contract_pin, indent=2) + "\n", encoding="utf-8"
    )
    add_asset_spec(
        specs,
        contract_path,
        roles=[VAOV + "asset-role/source-evidence"],
        representation=VAOV + "representation-status/authored",
        about=[instrument_id],
    )

    provenance = """# Cuntz Positiv VAO provenance and interpretation\n\nThis VAO was generated on 2026-08-24 from the audited `PositivXR` WAVE corpus and selected first-party Cuntz Unity application sources. The 225 WAVE files are copied byte-for-byte and remain the authoritative isolated-sample masters. Unity `Resources/Audio` duplicates are intentionally not included. AppleDouble files, generated Unity cache/build folders, third-party Resonance Audio demo scenes/assets, and the unrelated/uncertain Ariston model are excluded.\n\nThe source corpus identifies record `4010243`, five stop codes, and 45 keys. It does not establish a canonical historical instrument identity, historical tuning, physical survey scale, ownership, or a publication licence. Those facts are therefore not inferred. Rights remain unknown and access is restricted pending review.\n\nPlayable conformance uses 45 key controls, five independent stop toggles, and 225 configuration-scoped sample voice interactions. Each voice resolves exactly one WAVE asset and one reviewed parameter set, as required by VAO 0.2.2. Recorded pitch is preserved. Stop-label pitch offsets and A4=440 target frequencies are editorial runtime metadata, not measured tuning. The 0.3-second linear, voice-scoped release follows the source application's nominal fade duration while avoiding its legacy global-release behavior. No loop points are asserted.\n\nThe GLB files are Blender 5.1.1 derivatives of the retained FBX sources. Custom glTF extras preserve source object names and deterministic source-object indices. Nominal coordinate metadata is supplied for generic model viewing, but source scale has not been verified by physical survey; geometry must not be used as a dimensional authority. Standalone Unity animations are retained as source evidence but are not claimed as synchronized glTF animation capability.\n"""
    provenance_path = "payload/documentation/PROVENANCE.md"
    (workspace / provenance_path).write_text(provenance, encoding="utf-8")
    add_asset_spec(
        specs,
        provenance_path,
        roles=[VAOV + "asset-role/source-evidence"],
        representation=VAOV + "representation-status/authored",
        about=[instrument_id],
    )

    for name in ["CUNTZ_REFERENCE.md", "DECISIONS.md", "ARCHITECTURE.md", "TEST_STRATEGY.md"]:
        source = PROJECT_ROOT / "docs" / name
        destination_path = "payload/documentation/planning/" + name
        copy_file(source, workspace / destination_path)
        add_asset_spec(
            specs,
            destination_path,
            roles=[VAOV + "asset-role/source-evidence"],
            representation=VAOV + "representation-status/authored",
            about=[instrument_id],
            original=name,
        )

    inventory_path = "payload/documentation/SOURCE_INVENTORY.json"
    inventory_document = {
        "generatedAt": CREATED_AT,
        "included": source_inventory,
        "exclusions": [
            {
                "source": str(UNITY / "Assets/Resources/Audio"),
                "reason": "byte-duplicate playable samples; authoritative RAW corpus included once",
            },
            {
                "source": str(UNITY / "Assets/ResonanceAudio"),
                "reason": "third-party SDK/demo content, not Cuntz instrument evidence",
            },
            {"source": str(UNITY / "Library"), "reason": "generated Unity cache"},
            {
                "source": str(UNITY / "Assets/ariston_remap_v2.fbx"),
                "reason": "association with Cuntz instrument uncertain; inactive in relevant scene",
            },
            {"pattern": "._*", "reason": "AppleDouble filesystem metadata"},
        ],
        "counts": {"sampleMasters": 225, "stops": 5, "keys": 45, "sampleVoiceInteractions": 225},
    }
    (workspace / inventory_path).write_text(
        json.dumps(inventory_document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    add_asset_spec(
        specs,
        inventory_path,
        roles=[VAOV + "asset-role/source-evidence"],
        representation=VAOV + "representation-status/authored",
        about=[instrument_id],
    )

    assets: list[dict[str, Any]] = []
    for path in sorted(specs):
        digest, size = sha256_file(workspace / path)
        spec = specs[path]
        record = {
            "id": asset_id(path),
            "path": path,
            "mediaType": media_type(Path(path)),
            "byteSize": size,
            "sha256": digest,
            "roles": spec["roles"],
            "representationStatus": spec["representationStatus"],
            "aboutEntityIds": spec["aboutEntityIds"],
            "properties": spec["properties"],
        }
        if spec.get("originalFilename"):
            record["originalFilename"] = spec["originalFilename"]
        assets.append(record)

    main_model_id = model_assets["4010243_segmented.fbx"]
    relations.extend(
        [
            relation(instrument_id, VAO + "hasRepresentation", main_model_id, "accepted"),
            relation(
                instrument_id,
                VAO + "hasRepresentation",
                model_assets["4010243_segmented_03b2.fbx"],
                "accepted",
            ),
            relation(
                keyboard_id, VAO + "hasRepresentation", model_assets["positiv_keys.fbx"], "accepted"
            ),
            relation(experience_id, VAO + "presents", instrument_id, "accepted"),
            relation(experience_id, VAO + "usesModel", main_model_id, "accepted"),
        ]
    )

    model_activity_id = identifier("activity", "blender-model-conversion")
    inspection_activity_id = identifier("activity", "orgrec-corpus-inspection")
    authoring_activity_id = identifier("activity", "vao-authoring")
    paradata = [
        {
            "id": model_activity_id,
            "activityType": VAOV + "activity/model-conversion",
            "startedAt": CREATED_AT,
            "endedAt": CREATED_AT,
            "software": {
                "name": "Blender",
                "version": conversion["blenderVersion"],
                "uri": "https://www.blender.org/",
            },
            "method": {
                "methodType": "encoding",
                "representationStatus": "authored",
                "qualityFlags": [
                    "source-scale-unverified",
                    "standalone-unity-animation-not-converted",
                ],
            },
            "inputIds": [asset_id(model_source_paths[name]) for name in model_source_paths],
            "outputIds": list(model_assets.values()) + [asset_id(conversion_report_destination)],
            "parameters": {
                "format": "glTF 2.0 binary",
                "exportExtras": True,
                "exportAnimations": True,
                "upAxis": "+Y",
            },
            "notes": "FBX geometry was imported without semantic reconstruction. A Blender 5.1 light-import compatibility shim only restores a removed no-op shadow attribute.",
        },
        {
            "id": inspection_activity_id,
            "activityType": VAOV + "activity/corpus-inspection",
            "startedAt": "2026-08-19T00:00:00Z",
            "software": {"name": "OrgRec inspection and timbre validation", "version": "0.2.0-dev"},
            "method": {
                "methodType": "other",
                "representationStatus": "authored",
                "qualityFlags": [],
            },
            "inputIds": list(sample_asset_ids.values()),
            "outputIds": analysis_assets,
            "parameters": {
                "inspectionContract": inspection.get("inspectionContract"),
                "sampleCount": 225,
            },
        },
        {
            "id": authoring_activity_id,
            "activityType": VAOV + "activity/package-authoring",
            "startedAt": CREATED_AT,
            "endedAt": CREATED_AT,
            "software": {"name": "VAO-Blender Cuntz generator", "version": "1.0.0"},
            "method": {
                "methodType": "manual-authoring",
                "representationStatus": "authored",
                "qualityFlags": [
                    "rights-unknown",
                    "historical-identity-unverified",
                    "physical-scale-unverified",
                ],
            },
            "inputIds": [asset_id(inventory_path), asset_id(contract_path)],
            "outputIds": [asset_id(provenance_path)],
            "parameters": {
                "vaoVersion": FORMAT_VERSION,
                "interactionCount": 275,
                "sampleVoiceCount": 225,
            },
        },
    ]

    # Bind the runtime model after the conversion activity identifier exists.
    frame_id = identifier("coordinate-frame", "gltf-local")
    binding_id = identifier("geometry-binding", "instrument-main-model-root")
    manifest = {
        "$schema": SCHEMA,
        "@context": [CONTEXT],
        "type": "VirtualAcousticObject",
        "formatVersion": FORMAT_VERSION,
        "id": PACKAGE_ID,
        "revision": 1,
        "createdAt": CREATED_AT,
        "modifiedAt": CREATED_AT,
        "title": {"en": "Cuntz Positiv 4010243 — complete playable VAO"},
        "description": {
            "en": "A source-faithful, Blender-ready VAO with 225 high-resolution isolated WAVE masters, five independent stops, the observed 45-key short-octave compass, 225 scoped sample voices, retained Unity evidence, and glTF runtime models."
        },
        "conformsTo": [CORE, RESEARCH, PLAYABLE, SPATIAL, EXPERIENTIAL],
        "profiles": [
            {
                "id": CORE,
                "version": "0.2",
                "requiredCapabilities": [
                    VAOV + "capability/core-graph",
                    VAOV + "capability/fixity",
                ],
            },
            {
                "id": RESEARCH,
                "version": "0.2",
                "requiredCapabilities": [VAOV + "capability/paradata"],
            },
            {
                "id": PLAYABLE,
                "version": "0.2",
                "requiredCapabilities": [
                    VAOV + "capability/interaction",
                    VAOV + "capability/sampled-instrument-playback",
                ],
            },
            {
                "id": SPATIAL,
                "version": "0.2",
                "requiredCapabilities": [VAOV + "capability/spatial"],
            },
            {
                "id": EXPERIENTIAL,
                "version": "0.2",
                "requiredCapabilities": [VAOV + "capability/generic-model-viewing"],
            },
        ],
        "modavisBinding": {
            "ontologyIRI": "https://w3id.org/modavis/ontology",
            "ontologyVersion": "0.1.0-dev",
            "ontologyStatus": "development",
            "mappingVersion": "vao-modavis-mapping/0.2.2",
            "notes": "Private development binding; no public MODAVIS ontology release is asserted.",
        },
        "primaryEntityId": instrument_id,
        "focusEntityIds": [instrument_id, keyboard_id],
        "entities": entities,
        "relations": relations,
        "assets": assets,
        "paradata": paradata,
        "analyses": [],
        "acoustics": {
            "coordinateFrames": [
                {
                    "id": frame_id,
                    "dimension": 3,
                    "coordinateType": "cartesian",
                    "unit": QUDT_M,
                    "handedness": "right",
                    "upAxis": "+Y",
                    "forwardAxis": "-Z",
                    "generatedById": model_activity_id,
                    "notes": "Nominal glTF local frame. Source FBX scale is not physically verified.",
                }
            ],
            "poses": [],
            "geometryBindings": [
                {
                    "id": binding_id,
                    "subjectId": instrument_id,
                    "assetId": main_model_id,
                    "role": "runtime-visual",
                    "selector": {"selectorType": "gltf-node-index", "value": 0},
                    "frameId": frame_id,
                    "generatedById": model_activity_id,
                }
            ],
            "materialModels": [],
            "responseSets": [],
            "metricSets": [],
            "audioScenes": [],
            "renderConfigurations": [],
        },
        "rights": [
            {
                "appliesToIds": [PACKAGE_ID],
                "statement": {
                    "en": "Rights and licence for the supplied Cuntz audio, Unity sources, imagery, and models have not been established. Inclusion records technical provenance and does not grant reuse permission."
                },
                "accessCondition": "Restricted local research/development access pending rights-holder and licence review.",
                "creditLine": "Source record identifier 4010243; creator and rights holder not established in supplied evidence.",
            }
        ],
        "integrity": {
            "algorithm": "sha256",
            "assetCount": len(assets),
            "totalPayloadBytes": sum(item["byteSize"] for item in assets),
        },
        "extensions": {
            PROJECT + "generationSummary": {
                "sampleMasters": 225,
                "keyControls": 45,
                "stopControls": 5,
                "sampleVoiceInteractions": 225,
                "playableInteractionsTotal": 275,
                "sourceModelDerivatives": 3,
                "latestStandardAssessmentDate": "2026-08-24",
            }
        },
    }
    (workspace / "vao-manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "workspace": str(workspace),
                "assetCount": len(assets),
                "payloadBytes": manifest["integrity"]["totalPayloadBytes"],
                "entityCount": len(entities),
                "relationCount": len(relations),
                "interactionCount": sum(item["kind"] == "interaction" for item in entities),
            },
            indent=2,
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("workspace", type=Path)
    args = parser.parse_args()
    build(args.workspace.resolve())


if __name__ == "__main__":
    main()
