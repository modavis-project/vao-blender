"""Integrity verification for the exact VAO contracts supported by the extension."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import threading
from pathlib import Path
from types import ModuleType

RELEASE_BUNDLE_SHA256 = "76b55f33b09c94ad90aac79e8a599d007841e2c11288664f9c67987b4e68f328"
CONTRACT_ROOT = Path(__file__).resolve().parents[2] / "contract" / "vao-0.2.2"
FILE_SHA256 = {
    "vao-release-metadata.json": "6c5764208b796f08582e5bd68ba1610e080121caeb44ed13b37d48c7071afdd9",
    "vao-context.jsonld": "781122be3f9c098b42f0ee045c8f11d8eda120a1561224b049e6ca1b43d052bb",
    "vao-vocabulary.ttl": "71ad36568b2e805eef79af39b7bc08dcfd8a19d2032e48b59b18dbb940bc627b",
    "vao-manifest.schema.json": "c7a2cde4a68edca0a87068abfff88325a791b6c06fbe5d9025115046e27f7c3b",
    "modavis-audio-loop.ttl": "a6592fcf54997a00d6e52d279f2011be39d00a19d28b9127d888773ee53a0870",
}

RELEASE_BUNDLE_03_SHA256 = "fd4bf15b316b21cd926d7bc70d538951c36fee329d91f7b26ee601c38539f340"
CONTRACT_03_ROOT = Path(__file__).resolve().parents[2] / "contract" / "vao-0.3.2"
FILE_03_SHA256 = {
    "vao-specification-0.3.2-rc.zip": RELEASE_BUNDLE_03_SHA256,
    "Schemas/vao-manifest-0.3.schema.json": (
        "651cfe6b060cf2a4eb735c4b73446cbb84073095fde0995977c4d86293023fdd"
    ),
    "Schemas/vao-carrier-0.3.schema.json": (
        "b4bcc49aec153182885f67694f7031ef585bf997b5cf3ee12e08387e0211443e"
    ),
    "Docs/VAO_STANDARD_0.3.md": (
        "e6f64933ca2e17f664e1f91ff39e9e351584c2053ccc2cb2ef0ed3eb3cba3abb"
    ),
    "Docs/VAO_CONFORMANCE_0.3.md": (
        "014a9fdfcaaf68d3e1447abe17b8838d355e64f24c27d29549f8e404d7d4ef29"
    ),
    "Docs/VAO_ACOUSTIC_SCENES_0.3.md": (
        "e15d372bb1f334875a4aa3c1fbda18331d27e214ff8f74414acaefdbf3833647"
    ),
    "Docs/ORGREC_VAO_0.3.2_COMPATIBILITY.md": (
        "b81a455399cbac2a72a63945cefa347a3e1db1c1bf248ff2d62cca6eb89d3ca7"
    ),
    "Tools/vao03.py": "383ddd889386a32fe50200eb06862191356f6a607c4e405c0d2a2aacbda4f37b",
    "Tools/vaom.py": "fb0c27e5f5efa0fe1689fa01789a7f2985d8380669d558804e5bb90f498b024c",
    "BUILD_INFO.json": "5e5ef0785c6f5ab33bb10aec7e6af9474589424dd5849e7dd32dfbb87ecb431d",
    "Schemas/README.md": "1da1400cd9a18e2c7fb08c9a68dbc377424dee2ddda11f53288a18eef1adf24d",
    "Schemas/vao-context-0.3.jsonld": (
        "60e579c175149d06f967b76d5f880dc3fe6d7bb7325ed5225be108b6b72c45fb"
    ),
    "Schemas/vao-vocabulary-0.3.ttl": (
        "9afa8371a8df3dc9f6d1d7a5e48227627ef8d9209956ef592cec05576442b73e"
    ),
    "Schemas/vao-manifest.schema.json": (
        "c7a2cde4a68edca0a87068abfff88325a791b6c06fbe5d9025115046e27f7c3b"
    ),
    "Schemas/vao-release-0.3.schema.json": (
        "278ccc299329f61a8e2d5e01cbbed7431b3ebb8d7abb8e54c2144f0c0b721e01"
    ),
    "Schemas/vao-pack-manifest-0.3.schema.json": (
        "d4b04e54042d69b894a398cddcfd38af3eaaf94062c532dce5e8c03ac6578075"
    ),
    "Schemas/vao-materialization-receipt-0.3.schema.json": (
        "ed612de779dd415bbc2b1707e16f06e8ed05d8ecef6ab889eb3aed0438247c70"
    ),
    "Schemas/vao-zenodo-metadata-0.3.schema.json": (
        "6bb6a11d89a5baff71d0461a1bd6c29a51092e40580e5ab9f38be2faccbc81ea"
    ),
}

RELEASE_BUNDLE_04_SHA256 = "2acbda0a257c7f71e2b57e01617678745de2ecf11197b4687aa623f71d23955d"
CONTRACT_04_ROOT = Path(__file__).resolve().parents[2] / "contract" / "vao-0.4.0"
FILE_04_SHA256 = {
    "vao-standard-0.4.0.zip": RELEASE_BUNDLE_04_SHA256,
    "Schemas/vao-release-bundle-0.4.0.json": (
        "3ad51fac72ee71497bb82dbfb878fbf454c49d81e8a7ef879fdf8d28e9240e36"
    ),
    "Tools/vao03.py": "ff22f72bdf691e87f0101c682238cd2da933643dca86e82d318e3b75f87211ac",
    "Tools/vao04.py": "15e4e01c5904579cfa20b6a15b4ee71bece7340e5103c3180597b67d3948d095",
    "Tools/vao04_runtime.py": ("546d1b6b207b7359974541d80e00fae53a2aa53695db31ebd4d6e535a9a081dd"),
    "Tools/vao_resources.py": ("4af739d85c5d31ec6f87cf6074372904a27eec06a3d8543eb7123bcdf34297b1"),
    "Tools/vaom.py": "e52d11ccd5c6305345b6aac4f33949e4f1a1074e2c7374d031b6f35a36644eb0",
    "requirements-lock.txt": ("cfc21919a7f6c3eda016e2d2b37c75298bf7760469bb6938833dd60255feb30b"),
}

STANDARD_05_COMMIT = "d17b3f188fdf7fadd01ba025383e4feca8def935"
RELEASE_BUNDLE_05_SHA256 = "82efb6ee31353e72c81671e2c6500c51dc223d7f21af4983705933ea6caa5c96"
CONTRACT_05_ROOT = Path(__file__).resolve().parents[2] / "contract" / "vao-0.5.0"
FILE_05_SHA256 = {
    "Schemas/vao-release-bundle-0.5.0.json": RELEASE_BUNDLE_05_SHA256,
    "Schemas/vao-manifest-0.4.0.schema.json": (
        "3b8fba703654b8f5e42101e2ecc9fca769bf19115d01ae13d044a36c10fcbc83"
    ),
    "Tools/vao03.py": "ff22f72bdf691e87f0101c682238cd2da933643dca86e82d318e3b75f87211ac",
    "Tools/vao05.py": "5b83a33ae27259c6ef5c8d5bce44920743033e15e458cea368757baa17066513",
    "Tools/vao05_runtime.py": ("46fabdac8534f7c93b4e39f07bb2bdc6995637591384d3ad30c9b53c335d7847"),
    "Tools/vao_resources.py": ("4af739d85c5d31ec6f87cf6074372904a27eec06a3d8543eb7123bcdf34297b1"),
    "Tools/vaom.py": "e52d11ccd5c6305345b6aac4f33949e4f1a1074e2c7374d031b6f35a36644eb0",
    "requirements-lock.txt": "cfc21919a7f6c3eda016e2d2b37c75298bf7760469bb6938833dd60255feb30b",
}

_REFERENCE_LOCK = threading.Lock()
_REFERENCE_03: ModuleType | None = None
_REFERENCE_04: ModuleType | None = None
_REFERENCE_05: ModuleType | None = None


class ContractIntegrityError(RuntimeError):
    pass


def verify_contract() -> None:
    pin = CONTRACT_ROOT / "CONTRACT_SHA256"
    try:
        recorded = pin.read_text(encoding="ascii").split()[0]
    except (OSError, IndexError) as exc:
        raise ContractIntegrityError("VAO contract bundle pin is absent or unreadable") from exc
    if recorded != RELEASE_BUNDLE_SHA256:
        raise ContractIntegrityError(
            "VAO contract bundle pin does not match the supported snapshot"
        )
    for name, expected in FILE_SHA256.items():
        path = CONTRACT_ROOT / name
        try:
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError as exc:
            raise ContractIntegrityError(
                f"vendored VAO contract file is unavailable: {name}"
            ) from exc
        if actual != expected:
            raise ContractIntegrityError(f"vendored VAO contract file failed integrity: {name}")


def verify_contract_03() -> None:
    """Verify the exact implemented-editor-draft VAO 0.3.2 snapshot."""
    pin = CONTRACT_03_ROOT / "CONTRACT_SHA256"
    try:
        recorded = pin.read_text(encoding="ascii").split()[0]
    except (OSError, IndexError) as exc:
        raise ContractIntegrityError(
            "VAO 0.3.2 contract bundle pin is absent or unreadable"
        ) from exc
    if recorded != RELEASE_BUNDLE_03_SHA256:
        raise ContractIntegrityError("VAO 0.3.2 contract bundle pin does not match")
    for name, expected in FILE_03_SHA256.items():
        path = CONTRACT_03_ROOT / name
        try:
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError as exc:
            raise ContractIntegrityError(
                f"vendored VAO 0.3.2 contract file is unavailable: {name}"
            ) from exc
        if actual != expected:
            raise ContractIntegrityError(
                f"vendored VAO 0.3.2 contract file failed integrity: {name}"
            )


def verify_contract_04() -> None:
    """Verify the signed, published VAO 0.4.0 source and normative bundle."""
    pin = CONTRACT_04_ROOT / "CONTRACT_SHA256"
    try:
        recorded = pin.read_text(encoding="ascii").split()[0]
    except (OSError, IndexError) as exc:
        raise ContractIntegrityError(
            "VAO 0.4.0 contract bundle pin is absent or unreadable"
        ) from exc
    if recorded != RELEASE_BUNDLE_04_SHA256:
        raise ContractIntegrityError("VAO 0.4.0 contract bundle pin does not match")
    for name, expected in FILE_04_SHA256.items():
        path = CONTRACT_04_ROOT / name
        try:
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError as exc:
            raise ContractIntegrityError(
                f"vendored VAO 0.4.0 contract file is unavailable: {name}"
            ) from exc
        if actual != expected:
            raise ContractIntegrityError(
                f"vendored VAO 0.4.0 contract file failed integrity: {name}"
            )

    bundle_path = CONTRACT_04_ROOT / "Schemas" / "vao-release-bundle-0.4.0.json"
    try:
        bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
        artifacts = bundle["artifacts"]
    except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise ContractIntegrityError("VAO 0.4.0 normative artifact bundle is unreadable") from exc
    if bundle.get("formatVersion") != "0.4.0" or not isinstance(artifacts, list):
        raise ContractIntegrityError("VAO 0.4.0 normative artifact bundle has an invalid identity")
    for artifact in artifacts:
        try:
            name = str(artifact["path"])
            expected_size = int(artifact["byteSize"])
            expected_digest = str(artifact["sha256"])
            data = (CONTRACT_04_ROOT / name).read_bytes()
        except (OSError, KeyError, TypeError, ValueError) as exc:
            raise ContractIntegrityError(
                "VAO 0.4.0 normative artifact inventory is incomplete"
            ) from exc
        if len(data) != expected_size or hashlib.sha256(data).hexdigest() != expected_digest:
            raise ContractIntegrityError(
                f"vendored VAO 0.4.0 normative artifact failed integrity: {name}"
            )


def verify_contract_05() -> None:
    """Verify the commit-pinned VAO 0.5.0 candidate and normative bundle."""
    try:
        recorded = (CONTRACT_05_ROOT / "STANDARD_COMMIT").read_text(encoding="ascii").strip()
    except OSError as exc:
        raise ContractIntegrityError("VAO 0.5.0 contract commit pin is absent") from exc
    if recorded != STANDARD_05_COMMIT:
        raise ContractIntegrityError("VAO 0.5.0 contract commit pin does not match")
    for name, expected in FILE_05_SHA256.items():
        path = CONTRACT_05_ROOT / name
        try:
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError as exc:
            raise ContractIntegrityError(
                f"vendored VAO 0.5.0 contract file is unavailable: {name}"
            ) from exc
        if actual != expected:
            raise ContractIntegrityError(
                f"vendored VAO 0.5.0 contract file failed integrity: {name}"
            )

    bundle_path = CONTRACT_05_ROOT / "Schemas" / "vao-release-bundle-0.5.0.json"
    try:
        bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
        artifacts = bundle["artifacts"]
    except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise ContractIntegrityError("VAO 0.5.0 normative artifact bundle is unreadable") from exc
    if bundle.get("formatVersion") != "0.5.0" or not isinstance(artifacts, list):
        raise ContractIntegrityError("VAO 0.5.0 normative artifact bundle has an invalid identity")
    for artifact in artifacts:
        try:
            name = str(artifact["path"])
            expected_size = int(artifact["byteSize"])
            expected_digest = str(artifact["sha256"])
            data = (CONTRACT_05_ROOT / name).read_bytes()
        except (OSError, KeyError, TypeError, ValueError) as exc:
            raise ContractIntegrityError(
                "VAO 0.5.0 normative artifact inventory is incomplete"
            ) from exc
        if len(data) != expected_size or hashlib.sha256(data).hexdigest() != expected_digest:
            raise ContractIntegrityError(
                f"vendored VAO 0.5.0 normative artifact failed integrity: {name}"
            )


def verify_contracts() -> None:
    verify_contract()
    verify_contract_03()
    verify_contract_04()
    verify_contract_05()


def reference_validator_03() -> ModuleType:
    """Load the byte-pinned OrgRec 0.3.2 reference validator offline.

    The vendored files remain unmodified.  A temporary ``vaom`` module alias is
    installed only while executing ``vao03.py``, because that exact upstream
    source uses a sibling top-level import.
    """
    global _REFERENCE_03
    if _REFERENCE_03 is not None:
        return _REFERENCE_03
    with _REFERENCE_LOCK:
        if _REFERENCE_03 is not None:
            return _REFERENCE_03
        verify_contract_03()
        tools = CONTRACT_03_ROOT / "Tools"
        vaom_path = tools / "vaom.py"
        vao03_path = tools / "vao03.py"
        vaom = _module_from_path("_vao_blender_pinned_032_vaom", vaom_path)
        previous = sys.modules.get("vaom")
        sys.modules["vaom"] = vaom
        try:
            reference = _module_from_path("_vao_blender_pinned_032_reference", vao03_path)
        finally:
            if previous is None:
                sys.modules.pop("vaom", None)
            else:
                sys.modules["vaom"] = previous
        if getattr(reference, "FORMAT_VERSION", None) != "0.3.2":
            raise ContractIntegrityError("pinned VAO validator has an unexpected format version")
        _REFERENCE_03 = reference
        return reference


def _module_from_path(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ContractIntegrityError(f"cannot load pinned VAO module {path.name}")
    module = importlib.util.module_from_spec(spec)
    previous = sys.modules.get(name)
    previous_dont_write_bytecode = sys.dont_write_bytecode
    sys.modules[name] = module
    sys.dont_write_bytecode = True
    try:
        spec.loader.exec_module(module)
    except Exception:
        if previous is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = previous
        raise
    finally:
        sys.dont_write_bytecode = previous_dont_write_bytecode
    return module


def reference_validator_04() -> ModuleType:
    """Load the byte-pinned VAO 0.4.0 reference validator fully offline."""
    global _REFERENCE_04
    if _REFERENCE_04 is not None:
        return _REFERENCE_04
    with _REFERENCE_LOCK:
        if _REFERENCE_04 is not None:
            return _REFERENCE_04
        verify_contract_04()
        tools = CONTRACT_04_ROOT / "Tools"
        aliases = ("vao_resources", "vaom", "vao03", "vao04_runtime")
        previous = {name: sys.modules.get(name) for name in aliases}
        try:
            resources = _module_from_path(
                "_vao_blender_pinned_040_resources", tools / "vao_resources.py"
            )
            sys.modules["vao_resources"] = resources
            vaom = _module_from_path("_vao_blender_pinned_040_vaom", tools / "vaom.py")
            sys.modules["vaom"] = vaom
            vao03 = _module_from_path("_vao_blender_pinned_040_vao03", tools / "vao03.py")
            sys.modules["vao03"] = vao03
            runtime = _module_from_path(
                "_vao_blender_pinned_040_runtime", tools / "vao04_runtime.py"
            )
            sys.modules["vao04_runtime"] = runtime
            reference = _module_from_path("_vao_blender_pinned_040_reference", tools / "vao04.py")
        except ModuleNotFoundError as exc:
            raise ContractIntegrityError(
                "VAO 0.4.0 validation dependencies are unavailable; install the bundled wheels"
            ) from exc
        finally:
            for name, module in previous.items():
                if module is None:
                    sys.modules.pop(name, None)
                else:
                    sys.modules[name] = module
        if getattr(reference, "FORMAT_VERSION", None) != "0.4.0":
            raise ContractIntegrityError("pinned VAO validator has an unexpected format version")
        _REFERENCE_04 = reference
        return reference


def reference_validator_05() -> ModuleType:
    """Load the commit-pinned VAO 0.5.0 candidate validator fully offline."""
    global _REFERENCE_05
    if _REFERENCE_05 is not None:
        return _REFERENCE_05
    with _REFERENCE_LOCK:
        if _REFERENCE_05 is not None:
            return _REFERENCE_05
        verify_contract_05()
        tools = CONTRACT_05_ROOT / "Tools"
        aliases = ("vao_resources", "vaom", "vao03", "vao05_runtime")
        previous = {name: sys.modules.get(name) for name in aliases}
        try:
            resources = _module_from_path(
                "_vao_blender_pinned_050_resources", tools / "vao_resources.py"
            )
            sys.modules["vao_resources"] = resources
            vaom = _module_from_path("_vao_blender_pinned_050_vaom", tools / "vaom.py")
            sys.modules["vaom"] = vaom
            vao03 = _module_from_path("_vao_blender_pinned_050_vao03", tools / "vao03.py")
            sys.modules["vao03"] = vao03
            runtime = _module_from_path(
                "_vao_blender_pinned_050_runtime", tools / "vao05_runtime.py"
            )
            sys.modules["vao05_runtime"] = runtime
            reference = _module_from_path("_vao_blender_pinned_050_reference", tools / "vao05.py")
        except ModuleNotFoundError as exc:
            raise ContractIntegrityError(
                "VAO 0.5.0 validation dependencies are unavailable; install the bundled wheels"
            ) from exc
        finally:
            for name, module in previous.items():
                if module is None:
                    sys.modules.pop(name, None)
                else:
                    sys.modules[name] = module
        if getattr(reference, "FORMAT_VERSION", None) != "0.5.0":
            raise ContractIntegrityError("pinned VAO validator has an unexpected format version")
        _REFERENCE_05 = reference
        return reference
