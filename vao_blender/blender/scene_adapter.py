"""Transactional glTF materialization and generated control-surface helpers."""

from __future__ import annotations

import tempfile
from pathlib import Path

import bpy
from mathutils import Matrix

from ..core.gltf import inject_glb_node_indices
from ..core.vao03 import frame_to_root, matrix_inverse, matrix_multiply, pose_to_root

TRACE_KEYS = {
    "package": "vao_package_id",
    "revision": "vao_revision",
    "format": "vao_format_version",
    "manifest": "vao_manifest_sha256",
    "asset": "vao_asset_id",
    "asset_hash": "vao_asset_sha256",
    "release": "vao_release_id",
    "logical_asset": "vao_logical_asset_id",
    "realization": "vao_realization_id",
    "binding": "vao_geometry_binding_id",
    "frame": "vao_coordinate_frame_id",
    "archive": "vao_archive_sha256",
    "contract": "vao_contract_sha256",
    "materialization": "vao_materialization_id",
    "session": "vao_session_id",
}
TRACE_ROOT = "vao_materialization_root"

# Blender's glTF importer maps the glTF (+Y up, -Z forward) basis to Blender
# (+Z up, -Y forward).  Declared VAO frame matrices are composed against the
# inverse of this basis so the contract transform is applied exactly once.
GLTF_IMPORT_BASIS = (
    1.0,
    0.0,
    0.0,
    0.0,
    0.0,
    0.0,
    -1.0,
    0.0,
    0.0,
    1.0,
    0.0,
    0.0,
    0.0,
    0.0,
    0.0,
    1.0,
)


def _link_child(parent: bpy.types.Collection, name: str) -> bpy.types.Collection:
    child = bpy.data.collections.new(name)
    parent.children.link(child)
    return child


def _scene_collections(scene: bpy.types.Scene):
    seen: set[int] = set()
    stack = list(scene.collection.children)
    while stack:
        collection = stack.pop()
        pointer = collection.as_pointer()
        if pointer in seen:
            continue
        seen.add(pointer)
        yield collection
        stack.extend(collection.children)


def _materialization_roots(scene: bpy.types.Scene, materialization_id: str):
    return tuple(
        collection
        for collection in _scene_collections(scene)
        if collection.get(TRACE_ROOT)
        and str(collection.get(TRACE_KEYS["materialization"], "")) == materialization_id
    )


def _linked_scenes(root: bpy.types.Collection) -> tuple[bpy.types.Scene, ...]:
    return tuple(scene for scene in bpy.data.scenes if _collection_in_scene(scene, root))


def _resolve_session_root(
    session,
    scene: bpy.types.Scene,
    *,
    allow_initial_missing: bool,
) -> bpy.types.Collection | None:
    """Resolve a live root by durable identity and enforce unique scene ownership."""
    if not session.materialization_id:
        raise RuntimeError("live VAO session has no materialization identity")
    try:
        if session.scene != scene:
            raise RuntimeError("VAO session does not own the requested Blender scene")
    except ReferenceError as exc:
        raise RuntimeError("VAO session scene ownership is no longer valid") from exc
    matches = _materialization_roots(scene, session.materialization_id)
    if not matches:
        if allow_initial_missing and not session.root_collection_name:
            return None
        hint = (
            f" (last known as {session.root_collection_name!r})"
            if session.root_collection_name
            else ""
        )
        raise RuntimeError(
            "no managed VAO root with this materialization ID exists in the owning scene" + hint
        )
    if len(matches) != 1:
        raise RuntimeError(
            "multiple managed VAO roots claim this materialization ID in the owning scene; "
            "resolve the duplicate IDs before continuing"
        )
    root = matches[0]
    owners = _linked_scenes(root)
    if len(owners) != 1 or owners[0] != scene:
        raise RuntimeError(
            "managed VAO root is not linked exclusively to its owning scene; unlink it from "
            "every additional scene before continuing"
        )
    session.root_collection_name = root.name
    if hasattr(scene, "vao_runtime") and scene.vao_runtime.session_id == session.id:
        scene.vao_runtime.root_collection_name = root.name
    return root


def _resolve_detached_root(
    materialization_id: str,
    root_name_hint: str,
) -> tuple[bpy.types.Collection, bpy.types.Scene]:
    """Resolve a detached root globally by ID; a saved Blender name is only a hint."""
    if not materialization_id:
        raise RuntimeError("managed VAO removal requires a materialization ID")
    matches = tuple(
        collection
        for collection in bpy.data.collections
        if collection.get(TRACE_ROOT)
        and str(collection.get(TRACE_KEYS["materialization"], "")) == materialization_id
    )
    if not matches:
        hint = f" (last known as {root_name_hint!r})" if root_name_hint else ""
        raise RuntimeError("no managed VAO root has the requested materialization ID" + hint)
    if len(matches) != 1:
        raise RuntimeError(
            "multiple managed VAO roots claim the requested materialization ID; resolve the "
            "duplicate IDs before removal"
        )
    root = matches[0]
    owners = _linked_scenes(root)
    if len(owners) != 1:
        raise RuntimeError("managed VAO root must be linked to exactly one scene before removal")
    return root, owners[0]


def ensure_root(session, scene: bpy.types.Scene) -> bpy.types.Collection:
    existing = _resolve_session_root(session, scene, allow_initial_missing=True)
    if existing is not None:
        _assert_owned_subtree(existing, session.materialization_id)
        _retag_live_session(existing, session.id)
        return existing
    manifest = session.outcome.manifest
    title_value = manifest.get("title", {})
    title = title_value.get("en") or next(iter(title_value.values()), "Untitled")
    root = bpy.data.collections.new(f"VAO::{title}")
    scene.collection.children.link(root)
    root[TRACE_ROOT] = True
    root["vao_title"] = title
    root[TRACE_KEYS["package"]] = manifest.get("id", "")
    release = manifest.get("release", {})
    revision = (
        release.get("revision", 0) if hasattr(release, "get") else manifest.get("revision", 0)
    )
    root[TRACE_KEYS["revision"]] = revision
    root[TRACE_KEYS["format"]] = manifest.get("formatVersion", "")
    root[TRACE_KEYS["manifest"]] = session.outcome.manifest_sha256
    root[TRACE_KEYS["archive"]] = session.outcome.archive_sha256
    root[TRACE_KEYS["contract"]] = session.outcome.contract_sha256
    root[TRACE_KEYS["materialization"]] = session.materialization_id
    root[TRACE_KEYS["session"]] = session.id
    if hasattr(release, "get"):
        root[TRACE_KEYS["release"]] = release.get("id", "")
    root["vao_source_name"] = Path(session.source_path).name
    root["vao_materialization_version"] = "0.4.0"
    children = {}
    for name in ("Representations", "Controls", "Spatial", "Diagnostics"):
        child = _link_child(root, name)
        child["vao_collection_role"] = name
        children[name] = child
        child[TRACE_KEYS["package"]] = manifest.get("id", "")
        child[TRACE_KEYS["format"]] = manifest.get("formatVersion", "")
        child[TRACE_KEYS["manifest"]] = session.outcome.manifest_sha256
        child[TRACE_KEYS["archive"]] = session.outcome.archive_sha256
        child[TRACE_KEYS["contract"]] = session.outcome.contract_sha256
        child[TRACE_KEYS["materialization"]] = session.materialization_id
        child[TRACE_KEYS["session"]] = session.id
        if hasattr(release, "get"):
            child[TRACE_KEYS["release"]] = release.get("id", "")
    spatial = children["Spatial"]
    spatial.hide_viewport = True
    diagnostics = children["Diagnostics"]
    diagnostics.hide_viewport = True
    session.root_collection_name = root.name
    if hasattr(scene, "vao_runtime"):
        scene.vao_runtime.root_collection_name = root.name
        scene.vao_runtime.materialization_state = "READY"
    return root


def _retag_live_session(root: bpy.types.Collection, session_id: str) -> None:
    """Refresh ephemeral ownership after an exact relink without changing provenance."""
    stack = [root]
    seen: set[int] = set()
    while stack:
        collection = stack.pop()
        if collection.as_pointer() in seen:
            continue
        seen.add(collection.as_pointer())
        collection[TRACE_KEYS["session"]] = session_id
        stack.extend(collection.children)
        for obj in collection.objects:
            obj[TRACE_KEYS["session"]] = session_id


def _child(root: bpy.types.Collection, name: str) -> bpy.types.Collection:
    existing = _find_child(root, name)
    if existing:
        return existing
    child = _link_child(root, name)
    child["vao_collection_role"] = name
    for key in (
        TRACE_KEYS["package"],
        TRACE_KEYS["format"],
        TRACE_KEYS["manifest"],
        TRACE_KEYS["archive"],
        TRACE_KEYS["contract"],
        TRACE_KEYS["release"],
        TRACE_KEYS["materialization"],
        TRACE_KEYS["session"],
    ):
        if key in root:
            child[key] = root[key]
    return child


def _find_child(root: bpy.types.Collection, role: str) -> bpy.types.Collection | None:
    return next(
        (
            child
            for child in root.children
            if child.get("vao_collection_role") == role or child.name == role
        ),
        None,
    )


def _rollback(before: dict[str, set]) -> None:
    for obj in set(bpy.data.objects) - before["objects"]:
        bpy.data.objects.remove(obj, do_unlink=True)
    for collection in set(bpy.data.collections) - before["collections"]:
        bpy.data.collections.remove(collection)
    for category in ("meshes", "materials", "images", "armatures", "actions", "cameras", "lights"):
        datablocks = getattr(bpy.data, category)
        for item in set(datablocks) - before[category]:
            if item.users == 0:
                datablocks.remove(item)


def import_visual(
    session, scene: bpy.types.Scene, asset_id: str
) -> tuple[bpy.types.Collection, int]:
    if not session.media_ready(scene):
        raise RuntimeError(
            "verified media is unavailable for this result; complete validation, exact relink, "
            "and rights acknowledgement are required"
        )
    if bpy.context.scene is not None and bpy.context.scene != scene:
        raise RuntimeError("visual import must run in the owning scene context")
    is_modern = session.outcome.contract_line in {"0.3.2", "0.4.0", "0.5.0"}
    graph = session.outcome.graph
    if is_modern:
        acoustic_scene = session.outcome.acoustic_scene
        realization_id = asset_id or (
            acoustic_scene.runtime_visual_realization_id if acoustic_scene else ""
        )
        if realization_id in session.outcome.logical_assets and acoustic_scene:
            selected = session.outcome.realizations.get(
                acoustic_scene.runtime_visual_realization_id
            )
            if selected and selected.logical_asset_id == realization_id:
                realization_id = selected.id
        asset = session.outcome.realizations.get(realization_id)
        if asset is None:
            raise RuntimeError("selected VAO realization does not exist")
        if not acoustic_scene or realization_id != acoustic_scene.runtime_visual_realization_id:
            raise RuntimeError("selected realization is not the resolved runtime-visual geometry")
        if realization_id not in session.outcome.verified_assets:
            raise RuntimeError("runtime visual realization was not payload-fixity verified")
        visual_key = realization_id
    else:
        if graph is None or asset_id not in graph.assets:
            raise RuntimeError("selected visual asset does not exist")
        asset = graph.assets[asset_id]
        visual_key = asset.id
    if asset.media_type != "model/gltf-binary":
        raise RuntimeError("VAO-Blender materializes verified GLB assets; this remains inspectable")
    existing_root = _resolve_session_root(session, scene, allow_initial_missing=True)
    if existing_root:
        representations = _find_child(existing_root, "Representations")
        if representations:
            for existing in representations.children:
                if (
                    existing.get(TRACE_KEYS["asset"]) == asset.id
                    or existing.get(TRACE_KEYS["realization"]) == visual_key
                ):
                    return existing, len(existing.all_objects)

    before = {
        category: set(getattr(bpy.data, category))
        for category in (
            "objects",
            "collections",
            "meshes",
            "materials",
            "images",
            "armatures",
            "actions",
            "cameras",
            "lights",
        )
    }
    cache = session.cache
    verified_path = cache.extract(session.source_path, asset, protect=True)
    try:
        session.adopt_protected_cache_path(verified_path, cache.root)
    except Exception:
        cache.unregister_protected(verified_path)
        raise
    window = None
    try:
        window = bpy.context.window
        if window is not None:
            try:
                window.cursor_set("WAIT")
            except RuntimeError:
                window = None
        if hasattr(scene, "vao_runtime"):
            scene.vao_runtime.status_message = (
                f"Preparing verified model {asset.original_filename or asset.id}…"
            )
        with tempfile.TemporaryDirectory(prefix="vao-blender-gltf-") as directory:
            derivative = Path(directory) / f"{asset.sha256}.indexed.glb"
            inject_glb_node_indices(verified_path, derivative)
            result = bpy.ops.import_scene.gltf(
                filepath=str(derivative),
                import_scene_extras=True,
            )
            if "FINISHED" not in result:
                raise RuntimeError(f"Blender glTF importer returned {result}")
        imported = sorted(set(bpy.data.objects) - before["objects"], key=lambda item: item.name)
        if not imported:
            raise RuntimeError("Blender glTF importer created no objects")

        bindings = (
            []
            if is_modern
            else [
                item
                for item in session.outcome.manifest.get("acoustics", {}).get(
                    "geometryBindings", ()
                )
                if item.get("assetId") == asset.id
            ]
        )
        by_index = {
            int(obj["vao_blender_node_index"]): obj
            for obj in imported
            if "vao_blender_node_index" in obj
        }
        for binding in bindings:
            selector = binding.get("selector", {})
            if selector.get("selectorType") != "gltf-node-index":
                raise RuntimeError("required geometry binding uses an unsupported selector")
            index = int(selector.get("value", -1))
            target = by_index.get(index)
            if target is None:
                raise RuntimeError(f"required glTF node-index selector {index} did not resolve")
            binding_ids = {
                value
                for value in str(target.get("vao_geometry_binding_ids", "")).split("|")
                if value
            }
            entity_ids = {
                value for value in str(target.get("vao_entity_ids", "")).split("|") if value
            }
            binding_id = str(binding.get("id", ""))
            entity_id = str(binding.get("subjectId", ""))
            if binding_id:
                binding_ids.add(binding_id)
            if entity_id:
                entity_ids.add(entity_id)
            target["vao_geometry_binding_ids"] = "|".join(sorted(binding_ids))
            target["vao_entity_ids"] = "|".join(sorted(entity_ids))
            if "vao_geometry_binding_id" not in target:
                target["vao_geometry_binding_id"] = binding_id
            if "vao_entity_id" not in target:
                target["vao_entity_id"] = entity_id
            target["vao_selector_kind"] = "gltf-node-index"
            target["vao_selector_value"] = index

        declared_transform: tuple[float, ...] = ()
        common_root_id = ""
        if is_modern:
            technical = asset.technical_metadata
            source_frame_id = str(technical.get("coordinateFrameId", ""))
            common_root_id, declared_transform = frame_to_root(
                session.outcome.acoustic_scene.coordinate_frames, source_frame_id
            )
            expected_root = session.outcome.acoustic_scene.common_frame_root_id
            if not expected_root or common_root_id != expected_root:
                raise RuntimeError("visual geometry and acoustic measurements have no common frame")
            root_frame = session.outcome.acoustic_scene.coordinate_frames[common_root_id]
            if (
                root_frame.dimension != 3
                or root_frame.handedness != "right"
                or root_frame.up_axis != "+Z"
                or not root_frame.unit.endswith("/M")
            ):
                raise RuntimeError(
                    "runtime placement currently requires a right-handed metre +Z common root"
                )
            importer_compensation = matrix_inverse(GLTF_IMPORT_BASIS)
            delta = matrix_multiply(declared_transform, importer_compensation)
            delta_matrix = Matrix(
                tuple(tuple(delta[row * 4 + column] for column in range(4)) for row in range(4))
            )
            for obj in imported:
                obj.matrix_world = delta_matrix @ obj.matrix_world

        root = ensure_root(session, scene)
        representations = _child(root, "Representations")
        label = asset.original_filename or asset.id.rsplit(":", 1)[-1][:12]
        collection = bpy.data.collections.new(f"Representation::{label}")
        representations.children.link(collection)
        collection[TRACE_KEYS["asset"]] = asset.id
        collection[TRACE_KEYS["asset_hash"]] = asset.sha256
        collection[TRACE_KEYS["package"]] = session.outcome.manifest.get("id", "")
        collection[TRACE_KEYS["manifest"]] = session.outcome.manifest_sha256
        collection[TRACE_KEYS["archive"]] = session.outcome.archive_sha256
        collection[TRACE_KEYS["contract"]] = session.outcome.contract_sha256
        collection[TRACE_KEYS["materialization"]] = session.materialization_id
        collection[TRACE_KEYS["session"]] = session.id
        collection[TRACE_KEYS["format"]] = session.outcome.manifest.get("formatVersion", "")
        release = session.outcome.manifest.get("release", {})
        if hasattr(release, "get"):
            collection[TRACE_KEYS["release"]] = release.get("id", "")
        if is_modern:
            acoustic_scene = session.outcome.acoustic_scene
            binding = acoustic_scene.geometry_bindings[acoustic_scene.runtime_visual_binding_id]
            collection[TRACE_KEYS["logical_asset"]] = asset.logical_asset_id
            collection[TRACE_KEYS["realization"]] = asset.id
            collection[TRACE_KEYS["binding"]] = binding.id
            collection[TRACE_KEYS["frame"]] = str(
                asset.technical_metadata.get("coordinateFrameId", "")
            )
            collection["vao_common_frame_root_id"] = common_root_id
            collection["vao_declared_transform_row_major"] = list(declared_transform)
        for obj in imported:
            for owner in tuple(obj.users_collection):
                owner.objects.unlink(obj)
            collection.objects.link(obj)
            obj[TRACE_KEYS["package"]] = session.outcome.manifest.get("id", "")
            obj[TRACE_KEYS["asset"]] = asset.id
            obj[TRACE_KEYS["asset_hash"]] = asset.sha256
            obj["vao_generated"] = False
            obj[TRACE_KEYS["manifest"]] = session.outcome.manifest_sha256
            obj[TRACE_KEYS["archive"]] = session.outcome.archive_sha256
            obj[TRACE_KEYS["contract"]] = session.outcome.contract_sha256
            obj[TRACE_KEYS["materialization"]] = session.materialization_id
            obj[TRACE_KEYS["session"]] = session.id
            obj[TRACE_KEYS["format"]] = session.outcome.manifest.get("formatVersion", "")
            if hasattr(release, "get"):
                obj[TRACE_KEYS["release"]] = release.get("id", "")
            if is_modern:
                obj[TRACE_KEYS["logical_asset"]] = asset.logical_asset_id
                obj[TRACE_KEYS["realization"]] = asset.id
                obj[TRACE_KEYS["binding"]] = binding.id
                obj[TRACE_KEYS["frame"]] = str(
                    asset.technical_metadata.get("coordinateFrameId", "")
                )
                obj["vao_common_frame_root_id"] = common_root_id
                obj["vao_declared_transform_row_major"] = list(declared_transform)
                obj["vao_entity_ids"] = binding.subject_id
        if is_modern:
            _create_acoustic_markers(session, root, collection)
        for candidate in set(bpy.data.collections) - before["collections"] - {collection}:
            if (
                candidate not in {root, representations}
                and not candidate.objects
                and not candidate.children
            ):
                bpy.data.collections.remove(candidate)
        return collection, len(imported)
    except Exception:
        try:
            _rollback(before)
        finally:
            session.release_cache_path(verified_path)
        if session.root_collection_name not in bpy.data.collections:
            session.root_collection_name = ""
        raise
    finally:
        if window is not None:
            try:
                window.cursor_set("DEFAULT")
            except RuntimeError:
                pass


def _create_acoustic_markers(
    session,
    root: bpy.types.Collection,
    representation: bpy.types.Collection,
) -> None:
    """Create metadata-only source/receiver helpers in the common scene frame."""
    acoustic = session.outcome.acoustic_scene
    if acoustic is None:
        raise RuntimeError("validated VAO acoustic scene plan is unavailable")
    spatial = _child(root, "Spatial")
    spatial.hide_viewport = False
    spatial["vao_metadata_only"] = True
    spatial["vao_support_notice"] = (
        "RIR metadata only; no program-audio playback, convolution, or simulation"
    )
    rir_by_measurement = {
        measurement_id: rir
        for rir in acoustic.impulse_responses
        for measurement_id in rir.measurement_ids
    }
    for measurement in acoustic.measurements.values():
        response = next(
            (
                item
                for item in acoustic.response_sets.values()
                if measurement.id in item.measurement_ids
            ),
            None,
        )
        rir = rir_by_measurement.get(measurement.id)
        if response is None or rir is None:
            raise RuntimeError(f"measurement {measurement.id!r} has no resolved RIR response link")
        for role, entity_id, pose_id, display in (
            ("source", measurement.source_id, measurement.source_pose_id, "SPHERE"),
            ("receiver", measurement.receiver_id, measurement.receiver_pose_id, "CIRCLE"),
        ):
            pose = acoustic.poses[pose_id]
            root_id, pose_transform = pose_to_root(acoustic.coordinate_frames, pose)
            if root_id != acoustic.common_frame_root_id:
                raise RuntimeError(f"pose {pose.id!r} is disconnected from the common scene frame")
            obj = bpy.data.objects.new(f"VAO {role.title()}::{entity_id.rsplit(':', 1)[-1]}", None)
            obj.empty_display_type = display
            obj.empty_display_size = 0.12 if role == "source" else 0.16
            obj.matrix_world = Matrix(
                tuple(
                    tuple(pose_transform[row * 4 + column] for column in range(4))
                    for row in range(4)
                )
            )
            obj["vao_generated"] = True
            obj["vao_spatial_role"] = role
            obj["vao_entity_id"] = entity_id
            obj["vao_entity_ids"] = entity_id
            obj["vao_pose_id"] = pose.id
            obj["vao_measurement_id"] = measurement.id
            obj["vao_declared_position"] = list(pose.position)
            obj["vao_declared_orientation_xyzw"] = list(pose.orientation_xyzw)
            obj["vao_pose_transform_row_major"] = list(pose_transform)
            obj[TRACE_KEYS["frame"]] = pose.frame_id
            obj["vao_common_frame_root_id"] = root_id
            obj["vao_response_set_id"] = response.id
            obj["vao_rir_realization_id"] = rir.realization_id
            obj["vao_rir_path"] = rir.embedded_path
            obj["vao_rir_sha256"] = rir.sha256
            obj["vao_rir_sample_rate"] = rir.sample_rate
            obj["vao_rir_sample_count"] = rir.sample_count
            obj["vao_rir_channel_count"] = rir.channel_count
            obj["vao_rir_encoding"] = rir.encoding
            obj[TRACE_KEYS["package"]] = session.outcome.manifest.get("id", "")
            obj[TRACE_KEYS["manifest"]] = session.outcome.manifest_sha256
            obj[TRACE_KEYS["format"]] = session.outcome.contract_line
            obj[TRACE_KEYS["archive"]] = session.outcome.archive_sha256
            obj[TRACE_KEYS["contract"]] = session.outcome.contract_sha256
            obj[TRACE_KEYS["materialization"]] = session.materialization_id
            obj[TRACE_KEYS["session"]] = session.id
            release = session.outcome.manifest.get("release", {})
            if hasattr(release, "get"):
                obj[TRACE_KEYS["release"]] = release.get("id", "")
            spatial.objects.link(obj)
        representation["vao_response_set_id"] = response.id
        representation["vao_measurement_id"] = measurement.id
        representation["vao_rir_realization_id"] = rir.realization_id
        representation["vao_rir_path"] = rir.embedded_path
        representation["vao_rir_sha256"] = rir.sha256
        representation["vao_rir_status"] = rir.representation_status
        representation["vao_rir_encoding"] = rir.encoding
        representation["vao_rir_sample_rate"] = rir.sample_rate
        representation["vao_rir_sample_count"] = rir.sample_count
        representation["vao_rir_channel_count"] = rir.channel_count
        representation["vao_rir_provenance_ids"] = "|".join(rir.provenance_ids)
        representation["vao_rir_support"] = "metadata-only"


def _owned_datablocks(objects: set[bpy.types.Object]):
    owned_data = {
        (obj.data.bl_rna.identifier, obj.data.name) for obj in objects if obj.data is not None
    }
    owned_materials = {
        material.name
        for obj in objects
        if getattr(obj.data, "materials", None) is not None
        for material in obj.data.materials
        if material is not None
    }
    owned_images = {
        node.image.name
        for name in owned_materials
        for material in (bpy.data.materials.get(name),)
        if material is not None and material.node_tree is not None
        for node in material.node_tree.nodes
        if getattr(node, "image", None) is not None
    }
    owned_actions = {
        obj.animation_data.action.name
        for obj in objects
        if obj.animation_data is not None and obj.animation_data.action is not None
    }
    return owned_data, owned_materials, owned_images, owned_actions


def _remove_unused_datablocks(
    owned_data,
    owned_materials: set[str],
    owned_images: set[str],
    owned_actions: set[str],
) -> None:
    categories = {
        "Mesh": "meshes",
        "Curve": "curves",
        "Armature": "armatures",
        "Camera": "cameras",
        "Light": "lights",
    }
    for identifier, name in owned_data:
        category = categories.get(identifier)
        if not category:
            continue
        datablocks = getattr(bpy.data, category)
        data = datablocks.get(name)
        if data is not None and data.users == 0:
            datablocks.remove(data)
    for name in owned_materials:
        material = bpy.data.materials.get(name)
        if material is not None and material.users == 0:
            bpy.data.materials.remove(material)
    for name in owned_images:
        image = bpy.data.images.get(name)
        if image is not None and image.users == 0:
            bpy.data.images.remove(image)
    for name in owned_actions:
        action = bpy.data.actions.get(name)
        if action is not None and action.users == 0:
            bpy.data.actions.remove(action)


def _collection_subtree(root: bpy.types.Collection) -> set[bpy.types.Collection]:
    collections: set[bpy.types.Collection] = set()
    stack = [root]
    while stack:
        collection = stack.pop()
        if collection in collections:
            continue
        collections.add(collection)
        stack.extend(collection.children)
    return collections


def _assert_owned_subtree(
    root: bpy.types.Collection,
    materialization_id: str,
) -> tuple[set[bpy.types.Collection], set[bpy.types.Object]]:
    """Preflight a managed subtree before any unlink or global datablock removal."""
    collections = _collection_subtree(root)
    for collection in collections:
        actual = str(collection.get(TRACE_KEYS["materialization"], ""))
        if actual != materialization_id:
            state = "untagged" if not actual else f"owned by {actual!r}"
            raise RuntimeError(
                f"managed subtree contains collection {collection.name!r} that is {state}; "
                "move user collections out or restore the exact VAO ownership tag before removal"
            )
    objects = {obj for collection in collections for obj in collection.objects}
    for obj in objects:
        actual = str(obj.get(TRACE_KEYS["materialization"], ""))
        if actual != materialization_id:
            state = "untagged" if not actual else f"owned by {actual!r}"
            raise RuntimeError(
                f"managed subtree contains object {obj.name!r} that is {state}; move user objects "
                "out or restore the exact VAO ownership tag before removal"
            )
    return collections, objects


def _assert_no_external_collection_links(
    root: bpy.types.Collection,
    owned_collections: set[bpy.types.Collection],
    *,
    check_root: bool,
    allowed_root_parents: set[bpy.types.Collection] | None = None,
    allowed_root_scenes: set[bpy.types.Scene] | None = None,
) -> None:
    """Refuse global deletion when a managed subtree was separately linked by the user."""
    allowed_root_parents = allowed_root_parents or set()
    allowed_root_scenes = allowed_root_scenes or set()
    parents: dict[bpy.types.Collection, list[bpy.types.Collection]] = {
        collection: [] for collection in owned_collections
    }
    for parent in bpy.data.collections:
        for child in parent.children:
            if child in parents:
                parents[child].append(parent)
    for collection in owned_collections:
        if collection == root and not check_root:
            continue
        external_parents = [
            parent
            for parent in parents[collection]
            if parent not in owned_collections
            and not (collection == root and parent in allowed_root_parents)
        ]
        direct_scenes = [
            scene
            for scene in bpy.data.scenes
            if scene.collection.children.get(collection.name) == collection
            and not (collection == root and scene in allowed_root_scenes)
        ]
        if external_parents or direct_scenes:
            owners = [f"collection {parent.name}" for parent in external_parents]
            owners.extend(f"scene {scene.name}" for scene in direct_scenes)
            raise RuntimeError(
                f"managed collection {collection.name!r} is also linked from "
                f"{', '.join(owners)}; unlink that shared subtree before removal"
            )


def remove_materialization(
    session=None,
    *,
    root_name: str = "",
    materialization_id: str = "",
) -> None:
    """Remove only this session's managed scene root for explicit lifecycle cleanup."""
    root_name = root_name or (session.root_collection_name if session else "")
    materialization_id = materialization_id or (session.materialization_id if session else "")
    if session:
        owner_scene = session.scene
        root = _resolve_session_root(session, owner_scene, allow_initial_missing=False)
        assert root is not None
    else:
        root, owner_scene = _resolve_detached_root(materialization_id, root_name)
    owned_collections, objects = _assert_owned_subtree(root, materialization_id)
    owned_data, owned_materials, owned_images, owned_actions = _owned_datablocks(objects)
    child_collections = owned_collections - {root}
    _assert_no_external_collection_links(
        root,
        owned_collections,
        check_root=True,
        allowed_root_scenes={owner_scene},
    )
    if session:
        session.stop_audio()
    for obj in objects:
        external = [owner for owner in obj.users_collection if owner not in owned_collections]
        if external:
            for owner in tuple(obj.users_collection):
                if owner in owned_collections:
                    owner.objects.unlink(obj)
        else:
            bpy.data.objects.remove(obj, do_unlink=True)
    _remove_unused_datablocks(owned_data, owned_materials, owned_images, owned_actions)
    for collection in sorted(child_collections, key=lambda item: len(item.name), reverse=True):
        if collection.name in bpy.data.collections:
            bpy.data.collections.remove(collection)
    if root.name in bpy.data.collections:
        bpy.data.collections.remove(root)
    for text in tuple(bpy.data.texts):
        if materialization_id and text.get(TRACE_KEYS["materialization"]) == materialization_id:
            bpy.data.texts.remove(text)
    if session:
        session.root_collection_name = ""
        session.release_cache_paths()
        if hasattr(session.scene, "vao_runtime"):
            runtime = session.scene.vao_runtime
            if runtime.materialization_id == materialization_id:
                runtime.root_collection_name = ""
                runtime.materialization_state = "NONE"


def _collection_in_scene(scene: bpy.types.Scene, target: bpy.types.Collection) -> bool:
    seen: set[int] = set()

    def contains(collection: bpy.types.Collection) -> bool:
        if collection == target:
            return True
        pointer = collection.as_pointer()
        if pointer in seen:
            return False
        seen.add(pointer)
        return any(contains(child) for child in collection.children)

    return contains(scene.collection)


def representation_collection(
    session,
    identifier: str,
    *,
    strict: bool = False,
) -> bpy.types.Collection | None:
    try:
        root = _resolve_session_root(session, session.scene, allow_initial_missing=True)
    except RuntimeError:
        if strict:
            raise
        return None
    if root is None:
        return None
    representations = _find_child(root, "Representations")
    if representations is None:
        return None
    if str(representations.get(TRACE_KEYS["materialization"], "")) != session.materialization_id:
        if strict:
            raise RuntimeError("managed Representations collection has conflicting ownership")
        return None
    matches = tuple(
        collection
        for collection in representations.children
        if identifier
        in {
            str(collection.get(TRACE_KEYS["asset"], "")),
            str(collection.get(TRACE_KEYS["logical_asset"], "")),
            str(collection.get(TRACE_KEYS["realization"], "")),
        }
    )
    if len(matches) > 1:
        if strict:
            raise RuntimeError("multiple managed representations claim the selected identifier")
        return None
    if not matches:
        return None
    collection = matches[0]
    if str(collection.get(TRACE_KEYS["materialization"], "")) != session.materialization_id:
        if strict:
            raise RuntimeError("selected representation has conflicting ownership")
        return None
    return collection


def set_representation_hidden(session, identifier: str, hidden: bool) -> bpy.types.Collection:
    collection = representation_collection(session, identifier, strict=True)
    if collection is None:
        raise RuntimeError("selected representation has not been materialized in this scene")
    collection.hide_viewport = hidden
    collection.hide_render = hidden
    return collection


def remove_representation(session, identifier: str) -> None:
    """Remove one exact managed representation and no sibling materializations."""
    collection = representation_collection(session, identifier, strict=True)
    if collection is None:
        raise RuntimeError("selected representation has not been materialized in this scene")
    owned_collections, objects = _assert_owned_subtree(
        collection,
        session.materialization_id,
    )
    owned_data, owned_materials, owned_images, owned_actions = _owned_datablocks(objects)
    root = _resolve_session_root(session, session.scene, allow_initial_missing=False)
    representations = _find_child(root, "Representations") if root else None
    _assert_no_external_collection_links(
        collection,
        owned_collections,
        check_root=True,
        allowed_root_parents={representations} if representations else set(),
    )
    for obj in objects:
        external = [owner for owner in obj.users_collection if owner not in owned_collections]
        if external:
            for owner in tuple(obj.users_collection):
                if owner in owned_collections:
                    owner.objects.unlink(obj)
        else:
            bpy.data.objects.remove(obj, do_unlink=True)
    for child in sorted(owned_collections, key=lambda item: len(item.name), reverse=True):
        if child.name in bpy.data.collections:
            bpy.data.collections.remove(child)
    _remove_unused_datablocks(owned_data, owned_materials, owned_images, owned_actions)


def create_control_surface(session, scene: bpy.types.Scene) -> int:
    bundle = session.outcome.interaction_plans
    if not session.media_ready(scene):
        raise RuntimeError("package media is not ready for control materialization")
    if not bundle or not bundle.supported:
        raise RuntimeError("package has no fully supported compiled controls")
    if not bundle.gates and not bundle.selections:
        raise RuntimeError("supported interaction plan declares no materializable controls")
    root = ensure_root(session, scene)
    controls = _child(root, "Controls")
    existing = [
        obj
        for obj in controls.objects
        if obj.get("vao_generated") and not obj.get("vao_control_label_object")
    ]
    if existing:
        update_control_surface(session)
        return len(existing)

    created_objects: list[bpy.types.Object] = []
    mesh = bpy.data.meshes.new("VAO Control Unit Cube")
    try:
        mesh.from_pydata(
            [
                (-0.5, -0.5, -0.5),
                (0.5, -0.5, -0.5),
                (0.5, 0.5, -0.5),
                (-0.5, 0.5, -0.5),
                (-0.5, -0.5, 0.5),
                (0.5, -0.5, 0.5),
                (0.5, 0.5, 0.5),
                (-0.5, 0.5, 0.5),
            ],
            [],
            [(0, 1, 2, 3), (4, 7, 6, 5), (0, 4, 5, 1), (1, 5, 6, 2), (2, 6, 7, 3), (4, 0, 3, 7)],
        )
        mesh.update()
        notes = [gate.key_number for gate in bundle.gates]
        minimum = min(notes, default=0)
        black_classes = {1, 3, 6, 8, 10}
        package_id = session.outcome.manifest.get("id", "")
        for gate in bundle.gates:
            is_black = gate.key_number % 12 in black_classes
            obj = bpy.data.objects.new(f"VAO Key {gate.key_number}", mesh)
            obj.location = ((gate.key_number - minimum) * 0.13, 0.25 if is_black else 0.0, 0.0)
            obj.scale = (0.115, 0.55 if is_black else 0.9, 0.12)
            obj["vao_generated"] = True
            obj["vao_gate_id"] = gate.interaction_id
            obj["vao_key_number"] = gate.key_number
            obj["vao_control_label"] = gate.label
            obj[TRACE_KEYS["package"]] = package_id
            obj[TRACE_KEYS["materialization"]] = session.materialization_id
            obj[TRACE_KEYS["session"]] = session.id
            obj.show_name = True
            obj.show_in_front = True
            controls.objects.link(obj)
            created_objects.append(obj)
        for index, selection in enumerate(bundle.selections):
            obj = bpy.data.objects.new(f"VAO Stop {selection.label}", mesh)
            obj.location = ((index % 8) * 0.55, -1.2 - (index // 8) * 0.42, 0.0)
            obj.scale = (0.35, 0.25, 0.25)
            obj["vao_generated"] = True
            obj["vao_selection_id"] = selection.interaction_id
            obj["vao_configuration_id"] = selection.configuration_id
            obj["vao_control_label"] = selection.label
            obj["vao_selection_independent"] = selection.independent
            obj[TRACE_KEYS["package"]] = package_id
            obj[TRACE_KEYS["materialization"]] = session.materialization_id
            obj[TRACE_KEYS["session"]] = session.id
            obj.show_name = True
            obj.show_in_front = True
            controls.objects.link(obj)
            created_objects.append(obj)
        update_control_surface(session)
        return len(created_objects)
    except Exception:
        for obj in created_objects:
            bpy.data.objects.remove(obj, do_unlink=True)
        if mesh.users == 0:
            bpy.data.meshes.remove(mesh)
        raise


def update_control_surface(session) -> None:
    """Expose pressed/selected state without editing source representation materials."""
    try:
        root = _resolve_session_root(session, session.scene, allow_initial_missing=True)
        if root is not None:
            _assert_owned_subtree(root, session.materialization_id)
    except RuntimeError:
        return
    controls = _find_child(root, "Controls") if root else None
    if controls is None:
        return
    black_classes = {1, 3, 6, 8, 10}
    for obj in controls.objects:
        if obj.get(TRACE_KEYS["session"]) != session.id:
            continue
        gate_id = str(obj.get("vao_gate_id", ""))
        configuration_id = str(obj.get("vao_configuration_id", ""))
        if gate_id:
            pressed = gate_id in session.pressed_gates
            is_black = int(obj.get("vao_key_number", 0)) % 12 in black_classes
            obj.color = (
                (1.0, 0.35, 0.05, 1.0)
                if pressed
                else ((0.04, 0.04, 0.04, 1.0) if is_black else (0.85, 0.85, 0.78, 1.0))
            )
            obj["vao_control_active"] = pressed
        elif configuration_id:
            active = configuration_id in session.active_configurations
            obj.color = (0.08, 0.8, 0.18, 1.0) if active else (0.22, 0.24, 0.28, 1.0)
            obj["vao_control_active"] = active
