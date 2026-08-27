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
}

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


def ensure_root(session, scene: bpy.types.Scene) -> bpy.types.Collection:
    if session.root_collection_name:
        existing = bpy.data.collections.get(session.root_collection_name)
        if existing:
            return existing
    manifest = session.outcome.manifest
    title_value = manifest.get("title", {})
    title = title_value.get("en") or next(iter(title_value.values()), "Untitled")
    root = bpy.data.collections.new(f"VAO::{title}")
    scene.collection.children.link(root)
    root[TRACE_KEYS["package"]] = manifest.get("id", "")
    release = manifest.get("release", {})
    revision = (
        release.get("revision", 0) if hasattr(release, "get") else manifest.get("revision", 0)
    )
    root[TRACE_KEYS["revision"]] = revision
    root[TRACE_KEYS["format"]] = manifest.get("formatVersion", "")
    root[TRACE_KEYS["manifest"]] = session.outcome.manifest_sha256
    if hasattr(release, "get"):
        root[TRACE_KEYS["release"]] = release.get("id", "")
    root["vao_source_name"] = Path(session.source_path).name
    root["vao_materialization_version"] = "0.3.0"
    for name in ("Representations", "Controls", "Spatial", "Diagnostics"):
        child = _link_child(root, name)
        child[TRACE_KEYS["package"]] = manifest.get("id", "")
        child[TRACE_KEYS["format"]] = manifest.get("formatVersion", "")
        child[TRACE_KEYS["manifest"]] = session.outcome.manifest_sha256
        if hasattr(release, "get"):
            child[TRACE_KEYS["release"]] = release.get("id", "")
    spatial = root.children["Spatial"]
    spatial.hide_viewport = True
    diagnostics = root.children["Diagnostics"]
    diagnostics.hide_viewport = True
    session.root_collection_name = root.name
    return root


def _child(root: bpy.types.Collection, name: str) -> bpy.types.Collection:
    existing = root.children.get(name)
    return existing or _link_child(root, name)


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
    is_modern = session.outcome.contract_line in {"0.3.2", "0.4.0"}
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
    existing_root = (
        bpy.data.collections.get(session.root_collection_name)
        if session.root_collection_name
        else None
    )
    if existing_root:
        representations = existing_root.children.get("Representations")
        if representations:
            for existing in representations.children:
                if (
                    existing.get(TRACE_KEYS["asset"]) == asset.id
                    or existing.get(TRACE_KEYS["realization"]) == visual_key
                ):
                    return existing, len(existing.all_objects)

    verified_path = session.cache.extract(session.source_path, asset)
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
    try:
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
            target["vao_geometry_binding_id"] = binding.get("id", "")
            target["vao_entity_ids"] = binding.get("subjectId", "")
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
        _rollback(before)
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


def remove_materialization(session) -> None:
    """Remove only this session's managed scene root for explicit lifecycle cleanup."""
    root = (
        bpy.data.collections.get(session.root_collection_name)
        if session.root_collection_name
        else None
    )
    if root is None:
        session.root_collection_name = ""
        return
    objects = set(root.all_objects)
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
    child_collections: set[bpy.types.Collection] = set()

    def collect_children(collection: bpy.types.Collection) -> None:
        for child in collection.children:
            child_collections.add(child)
            collect_children(child)

    collect_children(root)
    for obj in objects:
        bpy.data.objects.remove(obj, do_unlink=True)
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
    for collection in sorted(child_collections, key=lambda item: len(item.name), reverse=True):
        if collection.name in bpy.data.collections:
            bpy.data.collections.remove(collection)
    if root.name in bpy.data.collections:
        bpy.data.collections.remove(root)
    session.root_collection_name = ""


def create_control_surface(session, scene: bpy.types.Scene) -> int:
    bundle = session.outcome.interaction_plans
    if not bundle:
        raise RuntimeError("package has no compiled controls")
    root = ensure_root(session, scene)
    controls = _child(root, "Controls")
    existing = [obj for obj in controls.objects if obj.get("vao_generated")]
    if existing:
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
        minimum = min(notes)
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
            obj[TRACE_KEYS["package"]] = package_id
            controls.objects.link(obj)
            created_objects.append(obj)
        for index, selection in enumerate(bundle.selections):
            obj = bpy.data.objects.new(f"VAO Stop {selection.label}", mesh)
            obj.location = (index * 0.45, -1.2, 0.0)
            obj.scale = (0.35, 0.25, 0.25)
            obj["vao_generated"] = True
            obj["vao_selection_id"] = selection.interaction_id
            obj["vao_configuration_id"] = selection.configuration_id
            obj[TRACE_KEYS["package"]] = package_id
            controls.objects.link(obj)
            created_objects.append(obj)
        return len(created_objects)
    except Exception:
        for obj in created_objects:
            bpy.data.objects.remove(obj, do_unlink=True)
        if mesh.users == 0:
            bpy.data.meshes.remove(mesh)
        raise
