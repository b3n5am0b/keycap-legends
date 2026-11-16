# SPDX-License-Identifier: MIT
"""Post-process a lib3mf-written 3MF into a Bambu Studio-friendly project.

Bambu Studio assigns filaments per part via ``Metadata/model_settings.config``
(``<metadata key="extruder" value="N"/>`` on each part). It expects one
assembly object whose components are the part meshes. lib3mf instead writes
each mesh as its own build item, so Bambu imports them as separate objects
with no filament mapping and every part must be assigned by hand.

This module rewrites the 3MF in place:
- mesh objects are kept as-is (geometry, names, colors)
- lib3mf's per-mesh component-wrapper objects and build items are replaced by
  a single assembly object referencing all meshes
- ``Metadata/model_settings.config`` is added, mapping each part name to a
  filament/extruder slot
"""

import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

CORE_NS = "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"


def _indent(elem: ET.Element, level: int = 0) -> None:
    pad = "\n" + " " * level
    if len(elem):
        if not elem.text or not elem.text.strip():
            elem.text = pad + " "
        for child in elem:
            _indent(child, level + 1)
            if not child.tail or not child.tail.strip():
                child.tail = pad + " "
        if not elem[-1].tail or not elem[-1].tail.strip():
            elem[-1].tail = pad
    elif level and (not elem.tail or not elem.tail.strip()):
        elem.tail = pad


def bambuify_3mf(path: Path | str, part_extruders: dict[str, int]) -> None:
    """Restructure a 3MF for Bambu Studio with filament assignments.

    Args:
        path: 3MF file written by build123d's Mesher.
        part_extruders: part label -> 1-based filament/extruder slot,
            e.g. {"cap body": 1, "legend": 2, "stem": 1}.
    """
    path = Path(path)
    with zipfile.ZipFile(path) as z:
        entries = {name: z.read(name) for name in z.namelist()}

    ET.register_namespace("", CORE_NS)
    ET.register_namespace(
        "m", "http://schemas.microsoft.com/3dmanufacturing/material/2015/02"
    )
    ET.register_namespace(
        "p", "http://schemas.microsoft.com/3dmanufacturing/production/2015/06"
    )
    root = ET.fromstring(entries["3D/3dmodel.model"].decode())
    resources = root.find(f"{{{CORE_NS}}}resources")
    build = root.find(f"{{{CORE_NS}}}build")

    # Partition objects: meshes (have geometry) vs lib3mf component wrappers
    mesh_objects = []
    for obj in list(resources.findall(f"{{{CORE_NS}}}object")):
        if obj.find(f"{{{CORE_NS}}}mesh") is not None:
            mesh_objects.append(obj)
        else:
            resources.remove(obj)
    if not mesh_objects:
        raise RuntimeError(f"No mesh objects found in {path}")

    # Single assembly object referencing every mesh. The id must not clash
    # with ANY resource id (lib3mf numbers materials and objects globally).
    assembly_id = (
        max(int(el.get("id")) for el in resources if el.get("id") is not None) + 1
    )
    assembly = ET.SubElement(
        resources, f"{{{CORE_NS}}}object", {"id": str(assembly_id), "type": "model"}
    )
    components = ET.SubElement(assembly, f"{{{CORE_NS}}}components")
    for obj in mesh_objects:
        ET.SubElement(
            components, f"{{{CORE_NS}}}component", {"objectid": obj.get("id")}
        )

    for item in list(build):
        build.remove(item)
    ET.SubElement(build, f"{{{CORE_NS}}}item", {"objectid": str(assembly_id)})

    _indent(root)
    entries["3D/3dmodel.model"] = (
        b'<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root)
    )

    # Bambu part/filament mapping
    object_name = re.sub(r"\.3mf$", "", path.name)
    cfg = ET.Element("config")
    obj_el = ET.SubElement(cfg, "object", {"id": str(assembly_id)})
    ET.SubElement(obj_el, "metadata", {"key": "name", "value": object_name})
    ET.SubElement(obj_el, "metadata", {"key": "extruder", "value": "1"})
    for obj in mesh_objects:
        label = obj.get("name", "part")
        extruder = part_extruders.get(label, 1)
        part = ET.SubElement(
            obj_el, "part", {"id": obj.get("id"), "subtype": "normal_part"}
        )
        ET.SubElement(part, "metadata", {"key": "name", "value": label})
        ET.SubElement(
            part,
            "metadata",
            {"key": "matrix", "value": "1 0 0 0 0 1 0 0 0 0 1 0 0 0 0 1"},
        )
        ET.SubElement(part, "metadata", {"key": "extruder", "value": str(extruder)})
    _indent(cfg)
    entries["Metadata/model_settings.config"] = (
        b'<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(cfg)
    )

    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in entries.items():
            z.writestr(name, data)


def write_plate_3mf(
    files: list[str] | list[Path],
    out: Path | str,
    part_extruders: dict[str, int],
    spacing: float = 4.0,
    bed_size: tuple[float, float] = (256.0, 256.0),
) -> None:
    """Merge per-key 3MFs (already bambuified) into one Bambu Studio plate.

    Every key becomes its own assembly object (parts keep their relative
    positions) placed on a grid via its build-item transform, with the
    filament of every part pre-assigned in ``Metadata/model_settings.config``.

    Args:
        files: per-key 3MF files written by ``bambuify_3mf``.
        out: plate 3MF to write.
        part_extruders: part label -> 1-based filament/extruder slot.
        spacing: gap between neighbouring keycaps (mm).
        bed_size: printable area (mm); the grid is centered on it.
    """
    ns = f"{{{CORE_NS}}}"
    ET.register_namespace("", CORE_NS)
    root = ET.Element(f"{ns}model", {"unit": "millimeter", "xml:lang": "en-US"})
    resources = ET.SubElement(root, f"{ns}resources")
    build = ET.SubElement(root, f"{ns}build")
    cfg = ET.Element("config")

    next_id = 1
    # (assembly id, min x, min y, width, depth) per key
    keys: list[tuple[int, float, float, float, float]] = []
    content_types = b""
    rels = b""

    for file in files:
        file = Path(file)
        with zipfile.ZipFile(file) as z:
            model = ET.fromstring(z.read("3D/3dmodel.model").decode())
            content_types = content_types or z.read("[Content_Types].xml")
            rels = rels or z.read("_rels/.rels")
        src_resources = model.find(f"{ns}resources")
        xs: list[float] = []
        ys: list[float] = []
        parts: list[tuple[int, str]] = []
        for obj in src_resources.findall(f"{ns}object"):
            mesh = obj.find(f"{ns}mesh")
            if mesh is None:
                continue
            for v in mesh.iter(f"{ns}vertex"):
                xs.append(float(v.get("x")))
                ys.append(float(v.get("y")))
            for tri in mesh.iter(f"{ns}triangle"):
                for attr in ("pid", "p1", "p2", "p3"):
                    tri.attrib.pop(attr, None)
            label = obj.get("name", "part")
            # Colors live in per-file material resources that are not
            # merged - filaments are assigned through the Bambu config
            new_obj = ET.SubElement(
                resources,
                f"{ns}object",
                {"id": str(next_id), "type": "model", "name": label},
            )
            new_obj.append(mesh)
            parts.append((next_id, label))
            next_id += 1
        if not parts:
            raise RuntimeError(f"No mesh objects found in {file}")

        assembly_id = next_id
        next_id += 1
        assembly = ET.SubElement(
            resources, f"{ns}object", {"id": str(assembly_id), "type": "model"}
        )
        components = ET.SubElement(assembly, f"{ns}components")
        obj_el = ET.SubElement(cfg, "object", {"id": str(assembly_id)})
        ET.SubElement(obj_el, "metadata", {"key": "name", "value": file.stem})
        ET.SubElement(obj_el, "metadata", {"key": "extruder", "value": "1"})
        for part_id, label in parts:
            ET.SubElement(components, f"{ns}component", {"objectid": str(part_id)})
            part = ET.SubElement(
                obj_el, "part", {"id": str(part_id), "subtype": "normal_part"}
            )
            ET.SubElement(part, "metadata", {"key": "name", "value": label})
            ET.SubElement(
                part,
                "metadata",
                {"key": "matrix", "value": "1 0 0 0 0 1 0 0 0 0 1 0 0 0 0 1"},
            )
            ET.SubElement(
                part,
                "metadata",
                {"key": "extruder", "value": str(part_extruders.get(label, 1))},
            )
        keys.append((assembly_id, min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)))

    # Row-wise grid: fill each row up to the usable bed width
    margin = 10.0
    usable_w = bed_size[0] - 2 * margin
    rows: list[list[tuple[int, float, float, float, float]]] = [[]]
    row_w = 0.0
    for key in keys:
        width = key[3]
        if rows[-1] and row_w + spacing + width > usable_w:
            rows.append([])
            row_w = 0.0
        row_w += (spacing if rows[-1] else 0.0) + width
        rows[-1].append(key)
    row_depths = [max(k[4] for k in row) for row in rows]
    total_d = sum(row_depths) + spacing * (len(rows) - 1)
    if total_d > bed_size[1] - 2 * margin:
        print(
            f"WARNING: plate needs {total_d:.0f}mm depth, bed has "
            f"{bed_size[1] - 2 * margin:.0f}mm usable - rearrange in the slicer"
        )

    # First row at the back of the bed, like reading order
    y_cursor = (bed_size[1] + total_d) / 2
    for row, depth in zip(rows, row_depths):
        width_sum = sum(k[3] for k in row) + spacing * (len(row) - 1)
        x_cursor = (bed_size[0] - width_sum) / 2
        y_cursor -= depth
        for assembly_id, min_x, min_y, width, key_depth in row:
            tx = x_cursor - min_x
            ty = y_cursor + (depth - key_depth) / 2 - min_y
            ET.SubElement(
                build,
                f"{ns}item",
                {
                    "objectid": str(assembly_id),
                    "transform": f"1 0 0 0 1 0 0 0 1 {tx:.4f} {ty:.4f} 0",
                },
            )
            x_cursor += width + spacing
        y_cursor -= spacing

    _indent(cfg)
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", content_types)
        z.writestr("_rels/.rels", rels)
        z.writestr(
            "3D/3dmodel.model",
            b'<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root),
        )
        z.writestr(
            "Metadata/model_settings.config",
            b'<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(cfg),
        )
