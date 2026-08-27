#!/usr/bin/env python3
"""Import selected Cuntz Unity FBX files and export Blender-ready GLB derivatives."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import bpy
from mathutils import Vector


def patch_blender_51_fbx_light_regression() -> None:
    """Restore the removed compatibility attribute expected by Blender's FBX add-on."""
    probe = bpy.data.lights.new(name="VAO FBX compatibility probe", type="POINT")
    cycles_type = type(probe.cycles)
    if not hasattr(cycles_type, "cast_shadow"):
        setattr(
            cycles_type,
            "cast_shadow",
            property(lambda self: True, lambda self, value: None),
        )
    bpy.data.lights.remove(probe)


def user_args() -> list[str]:
    return sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []


def reset_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for collection in (bpy.data.meshes, bpy.data.materials, bpy.data.images, bpy.data.actions):
        for item in list(collection):
            collection.remove(item)


def import_fbx(path: Path) -> None:
    if hasattr(bpy.ops, "import_scene") and hasattr(bpy.ops.import_scene, "fbx"):
        bpy.ops.import_scene.fbx(filepath=str(path), use_anim=True)
    else:
        bpy.ops.wm.fbx_import(filepath=str(path), use_anim=True)


def world_bounds(objects: list[bpy.types.Object]) -> tuple[list[float], list[float]]:
    points: list[Vector] = []
    for obj in objects:
        if obj.type == "MESH":
            points.extend(obj.matrix_world @ Vector(corner) for corner in obj.bound_box)
    if not points:
        return [0.0, 0.0, 0.0], [0.0, 0.0, 0.0]
    return (
        [min(point[index] for point in points) for index in range(3)],
        [max(point[index] for point in points) for index in range(3)],
    )


def convert(source: Path, output: Path) -> dict[str, object]:
    reset_scene()
    import_fbx(source)
    objects = sorted(bpy.context.scene.objects, key=lambda item: item.name)
    for index, obj in enumerate(objects):
        obj["vao_source_object_name"] = obj.name
        obj["vao_source_object_index"] = index
        obj["vao_source_fbx"] = source.name

    minimum, maximum = world_bounds(objects)
    dimensions = [maximum[index] - minimum[index] for index in range(3)]
    mesh_objects = [obj for obj in objects if obj.type == "MESH"]
    report = {
        "source": str(source),
        "output": str(output),
        "objectCount": len(objects),
        "meshObjectCount": len(mesh_objects),
        "vertexCount": sum(len(obj.data.vertices) for obj in mesh_objects),
        "polygonCount": sum(len(obj.data.polygons) for obj in mesh_objects),
        "materialCount": len(
            {
                slot.material.name
                for obj in mesh_objects
                for slot in obj.material_slots
                if slot.material
            }
        ),
        "actionCount": len(bpy.data.actions),
        "bounds": {"minimumXYZ": minimum, "maximumXYZ": maximum, "dimensionsXYZ": dimensions},
        "objects": [
            {
                "name": obj.name,
                "type": obj.type,
                "parent": obj.parent.name if obj.parent else None,
                "data": obj.data.name if obj.data else None,
            }
            for obj in objects
        ],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.export_scene.gltf(
        filepath=str(output),
        export_format="GLB",
        export_extras=True,
        export_animations=True,
        export_yup=True,
        export_apply=False,
        export_cameras=False,
        export_lights=False,
    )
    report["outputByteSize"] = output.stat().st_size
    return report


def main() -> None:
    args = user_args()
    if len(args) < 3:
        raise SystemExit(
            "usage: blender --background --python SCRIPT -- OUTPUT_DIR REPORT_JSON FBX..."
        )
    output_dir = Path(args[0]).resolve()
    report_path = Path(args[1]).resolve()
    sources = [Path(value).resolve() for value in args[2:]]
    patch_blender_51_fbx_light_regression()
    report = {
        "generator": "Blender",
        "blenderVersion": bpy.app.version_string,
        "derivativePolicy": "Geometry-preserving FBX import and glTF 2.0 binary export; no semantic reconstruction inferred.",
        "models": [convert(source, output_dir / f"{source.stem}.glb") for source in sources],
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
