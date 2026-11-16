# SPDX-License-Identifier: MIT

import argparse
import math
from pathlib import Path

from build123d import (
    Align,
    Axis,
    BoundBox,
    Box,
    BuildSketch,
    Sketch,
    Color,
    Compound,
    Cylinder,
    Kind,
    Mesher,
    Part,
    Plane,
    Pos,
    Rot,
    ShapeList,
    Solid,
    Text,
    Unit,
    Vector,
    extrude,
    fillet,
    import_step,
    mirror,
    offset,
)
from OCP.BRepAlgoAPI import BRepAlgoAPI_Common, BRepAlgoAPI_Cut
from OCP.TopTools import TopTools_ListOfShape

from config import load_config
from models import SLOTS, LegendEntry, LegendSettings
from utils.bambu_project import bambuify_3mf, write_plate_3mf
from utils.mesher_patch import apply_mesher_triangulation_none_guard
from utils.stl_to_step import convert_stl_to_step

# Preview colors per legend slot (the slicer assigns the real filaments)
SLOT_COLORS: tuple[str, ...] = ("black", "red", "blue", "green")

# Characters that need safe filenames
FILENAME_MAP: dict[str, str] = {
    "<": "less",
    ">": "greater",
    "/": "slash",
    ":": "colon",
    "\\": "backslash",
    "|": "pipe",
    "?": "question",
    "*": "asterisk",
    '"': "quote",
}


def fuzzy_boolean(a: Part, b: Part, cut: bool) -> Part | None:
    """Boolean with fuzzy tolerance - fallback when exact booleans fail.

    OCCT's exact booleans can silently return nothing when tool faces are
    tangent to the target (e.g. arc-joined offset text). A small fuzzy value
    merges the near-coincident geometry and lets the operation succeed.
    """
    op = BRepAlgoAPI_Cut() if cut else BRepAlgoAPI_Common()
    args = TopTools_ListOfShape()
    args.Append(a.wrapped)
    tools = TopTools_ListOfShape()
    tools.Append(b.wrapped)
    op.SetArguments(args)
    op.SetTools(tools)
    op.SetFuzzyValue(1e-5)
    op.Build()
    if not op.IsDone():
        return None
    return Compound(op.Shape())  # type: ignore[return-value]


def build_choc_stem() -> Part:
    """Build the Kailh Choc stem geometry."""
    # Cross is used for alignment reference only, not included in the final stem
    stem: Part = Box(1.3, 3, 3.1, align=(Align.CENTER, Align.CENTER, Align.MAX)) - [
        Pos(3.9, 0),
        Pos(-3.9, 0),
    ] * Cylinder(3.4, 3.1, align=(Align.CENTER, Align.CENTER, Align.MAX))
    stem = fillet(stem.edges().group_by(Axis.Z)[:-1], 0.15)  # type: ignore[arg-type]
    return Pos(2.85, 0) * stem + Pos(-2.85, 0) * stem  # type: ignore[return-value]


def build_legend_desc(entry: LegendEntry) -> str | None:
    """Build a description string for the legend entry."""
    if entry.primary and entry.secondary and entry.tertiary:
        return f"{entry.primary}+{entry.secondary}+{entry.tertiary}"
    elif entry.primary and entry.secondary:
        return f"{entry.primary}+{entry.secondary}"
    elif entry.primary and entry.tertiary:
        return f"{entry.primary}+{entry.tertiary}"
    elif entry.primary:
        return entry.primary
    elif entry.secondary:
        return entry.secondary
    return None


def build_filename(entry: LegendEntry, row_name: str) -> str:
    """Build a safe filename for the keycap."""
    parts: list[str] = []
    if entry.name:
        parts.append(entry.name)
    elif entry.primary:
        parts.append(FILENAME_MAP.get(entry.primary, entry.primary))
    if entry.secondary:
        parts.append(FILENAME_MAP.get(entry.secondary, entry.secondary))
    if entry.tertiary:
        parts.append(FILENAME_MAP.get(entry.tertiary, entry.tertiary))
    return f"results/K_{'_'.join(parts)}_{row_name}.3mf"


def probe_top_surface_z(
    cap: Part, bbox: BoundBox, footprint: BoundBox, samples: int = 4
) -> float | None:
    """Lowest point of the cap's top surface under a legend footprint.

    Shoots vertical lines through a grid over the footprint and takes the
    highest hit of each (the outer top surface). Unlike the vertex scan in
    `find_legend_plane_z` this also works on smooth dished tops, which have
    no vertices inside the legend area. Returns None when nothing is hit.
    """
    wall_inset = 1.0
    x_min = max(footprint.min.X, bbox.min.X + wall_inset)
    x_max = min(footprint.max.X, bbox.max.X - wall_inset)
    y_min = max(footprint.min.Y, bbox.min.Y + wall_inset)
    y_max = min(footprint.max.Y, bbox.max.Y - wall_inset)
    if x_min > x_max or y_min > y_max:
        return None
    tops: list[float] = []
    for i in range(samples):
        for j in range(samples):
            x = x_min + (x_max - x_min) * i / (samples - 1)
            y = y_min + (y_max - y_min) * j / (samples - 1)
            hits = cap.find_intersection_points(
                Axis((x, y, bbox.min.Z - 1), (0, 0, 1))
            )
            if hits:
                tops.append(max(point.Z for point, _ in hits))
    return min(tops) if tops else None


def find_legend_plane_z(
    cap: Part, bbox: BoundBox, footprint: BoundBox | None = None
) -> float:
    """Find the Z coordinate for legend placement.

    Returns the minimum Z among top-surface vertices (top 60% by height)
    within the legend footprint - by default a 3mm radius around center,
    or the actual text extent when `footprint` is given. On slanted caps
    the surface keeps dropping toward the edges, so using the real
    footprint prevents glyph corners from ending up below the text solid.
    """
    cap_top_z = bbox.max.Z
    cap_bottom_z = bbox.min.Z
    cap_height = cap_top_z - cap_bottom_z

    # Only consider the upper portion (top 60%)
    z_threshold = cap_bottom_z + cap_height * 0.4

    if footprint is not None:
        # Clamp away from the side walls so wall vertices don't drag z down
        margin = 0.3
        wall_inset = 1.5
        x_min = max(footprint.min.X - margin, bbox.min.X + wall_inset)
        x_max = min(footprint.max.X + margin, bbox.max.X - wall_inset)
        y_min = max(footprint.min.Y - margin, bbox.min.Y + wall_inset)
        y_max = min(footprint.max.Y + margin, bbox.max.Y - wall_inset)
    else:
        x_min = y_min = -3.0
        x_max = y_max = 3.0

    candidate_z_values: list[float] = []
    for vertex in cap.vertices():
        v = vertex.center()
        if x_min < v.X < x_max and y_min < v.Y < y_max and v.Z > z_threshold:
            candidate_z_values.append(v.Z)

    if candidate_z_values:
        return min(candidate_z_values)

    # Fallback
    return cap_top_z



def resolve_slots(
    entry: LegendEntry, settings: LegendSettings
) -> list[tuple[int, str, str, float, float, float, float]]:
    """Resolve the legend slots of an entry.

    Returns one tuple per non-empty slot:
    (slot index 1-4, text, font, size, x offset, y offset, bold offset).
    Every slot is independent: it is drawn whenever it has content.
    """
    primary_font = entry.primary_font or settings.font
    default_fonts = {
        "primary": primary_font,
        "secondary": primary_font,
        "tertiary": settings.font,
        "quaternary": settings.font,
    }
    slots: list[tuple[int, str, str, float, float, float, float]] = []
    for index, slot in enumerate(SLOTS, start=1):
        text = getattr(entry, slot)
        if not text:
            continue

        def pick(suffix: str, slot: str = slot) -> float:
            value = getattr(entry, f"{slot}_{suffix}")
            return getattr(settings, f"{slot}_{suffix}") if value is None else value

        bold = settings.bold_offset if index == 1 else settings.small_bold_offset
        slots.append(
            (
                index,
                text,
                getattr(entry, f"{slot}_font") or default_fonts[slot],
                pick("font_size"),
                pick("x_offset"),
                pick("y_offset"),
                bold,
            )
        )
    if len(slots) == 1 and settings.center_single_legend:
        index, text, font, size, _, _, bold = slots[0]
        slots = [(index, text, font, size, 0.0, 0.0, bold)]
    return slots


def solids_of(shape: object) -> list[Solid]:
    """Solids of a boolean result (which may be None, a ShapeList or a shape)."""
    if shape is None:
        return []
    if isinstance(shape, ShapeList):
        return [s for item in shape for s in item.solids()]
    return list(shape.solids())  # type: ignore[attr-defined]


def carve_legends(
    cap: Part, tools: list[tuple[int, Part]]
) -> tuple[list[Solid], dict[int, list[Solid]]] | None:
    """Cut the legend tools out of the cap and extract one legend per slot.

    Escalating strategies: tangent tool faces can silently break OCCT
    booleans; a fuzzy tolerance or a sub-print-resolution nudge (8um)
    resolves them. Returns (cap solids, {slot index: legend solids}); the
    largest cap solid is the body, any others are detached islands.

    The slots are cut one after another: a single cut with the union of
    all tools fails on some caps where each individual cut succeeds.
    """
    min_body_volume = cap.volume * 0.5

    def good(solids: list[Solid]) -> list[Solid]:
        # A broken boolean can return inverted or fragment-only results
        solids = [s for s in solids if s.volume > 0]
        if solids and max(s.volume for s in solids) < min_body_volume:
            return []
        return solids

    for strategy, shift in (("exact", None), ("nudged", Pos(0.008, 0.008, 0))):
        shifted = [(i, t if shift is None else shift * t) for i, t in tools]
        body: Part | Solid = cap
        islands: list[Solid] = []
        legends: dict[int, list[Solid]] = {}
        for index, tool in shifted:
            cut_solids = good(solids_of(body - tool))  # type: ignore[operator]
            if not cut_solids:
                cut_solids = good(solids_of(fuzzy_boolean(body, tool, cut=True)))  # type: ignore[arg-type]
            if not cut_solids:
                break
            body = max(cut_solids, key=lambda s: s.volume)
            islands += [s for s in cut_solids if s is not body]
            solids = [s for s in solids_of(cap & tool) if s.volume > 0]  # type: ignore[operator]
            if not solids:
                solids = [
                    s
                    for s in solids_of(fuzzy_boolean(cap, tool, cut=False))
                    if s.volume > 0
                ]
            if not solids:
                break
            legends[index] = solids
        else:
            if strategy != "exact":
                print(f"    (used {strategy} boolean strategy)")
            return [body, *islands], legends  # type: ignore[list-item]
    return None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate keycaps with legends.")
    parser.add_argument(
        "--config", default="config.toml", help="TOML or JSON config file"
    )
    parser.add_argument(
        "--only-rows", nargs="+", metavar="ROW", help="only process these row groups"
    )
    parser.add_argument(
        "--only", nargs="+", metavar="KEY", help="only process these key names"
    )
    parser.add_argument(
        "--plate",
        metavar="FILE",
        help="also write one combined Bambu Studio plate with all generated keys",
    )
    parser.add_argument(
        "--view", action="store_true", help="show each key in the ocp_vscode viewer"
    )
    return parser.parse_args()


def main() -> None:
    """Main entry point for keycap generation."""
    args = parse_args()
    apply_mesher_triangulation_none_guard()

    show = None
    if args.view:
        from ocp_vscode import Camera, set_defaults, show

        set_defaults(reset_camera=Camera.CENTER, helper_scale=1, transparent=False)

    # Load configuration
    cfg = load_config(args.config)
    settings = cfg.settings
    part_extruders: dict[str, int] = {
        "cap body": settings.body_filament,
        "stem": settings.stem_filament,
        **{f"legend_{i}": settings.slot_filament(i) for i in range(1, len(SLOTS) + 1)},
    }
    Path("results").mkdir(exist_ok=True)
    written: list[str] = []
    failed: list[str] = []

    # Build stem geometry once
    choc_stem_base: Part = build_choc_stem()

    for row_name, legend_entries in cfg.legends.items():
        # Skip rows not in the --only-rows filter (if set)
        if args.only_rows and row_name not in args.only_rows:
            print(f"Skipping {row_name} (not in --only-rows)")
            continue

        print(f"Processing {row_name}...")

        # Get STEP file config
        if row_name not in cfg.step_files:
            raise SystemExit(f"legends.{row_name} has no matching step_files.{row_name}")
        step_cfg = cfg.step_files[row_name]
        if not Path(step_cfg.path).exists():
            if step_cfg.stl and Path(step_cfg.stl).exists():
                print(f"  {step_cfg.path} missing - converting from {step_cfg.stl}")
                try:
                    convert_stl_to_step(step_cfg.stl, step_cfg.path)
                except RuntimeError as e:
                    print(f"  SKIPPING {row_name}: STL conversion failed: {e}")
                    continue
            else:
                print(
                    f"  SKIPPING {row_name}: {step_cfg.path} missing "
                    "and no STL fallback"
                )
                continue
        cap: Part = import_step(step_cfg.path)  # type: ignore[assignment]
        if step_cfg.rotation != 0:
            cap = Rot(0, 0, step_cfg.rotation) * cap
        bbox = cap.bounding_box()
        cap = Pos(-bbox.center().X, -bbox.center().Y, -bbox.min.Z) * cap
        # Update bbox after repositioning
        bbox = cap.bounding_box()

        choc_stem: Part | None = None
        if not step_cfg.has_stem:
            # Stem plane: based on the largest face (inside bottom of keycap)
            internal_face = max(cap.faces(), key=lambda f: f.area)
            n: Vector = internal_face.normal_at()
            pln: Plane = Plane(
                origin=Vector(0, 0, internal_face.center().Z),
                z_dir=-n,
                x_dir=Vector(1, 0, 0),
            )
            choc_stem = pln.location * choc_stem_base
            choc_stem.color = Color("gray")
            choc_stem.label = "stem"

        # Legend plane: based on the lowest point of the top surface near the center
        legend_z = find_legend_plane_z(cap, bbox)
        text_pln: Plane = Plane(
            origin=Vector(0, 0, legend_z - 0.4),
            z_dir=Vector(0, 0, 1),
            x_dir=Vector(1, 0, 0),
        )

        for entry in legend_entries:
            key_name = entry.name or entry.primary
            slots = resolve_slots(entry, settings)
            if not slots:
                print("  Skipping: no legend specified")
                continue
            if args.only and key_name not in args.only:
                continue
            legend_desc = "+".join(text for _, text, *_ in slots)

            print(
                f"  Creating keycap {key_name or ''} with legend: {legend_desc}"
                + (" (mirrored)" if entry.mirror_x else "")
            )

            # Mirror cap and stem BEFORE boolean operations, so legend aligns correctly
            working_cap: Part
            working_stem: Part | None = None
            if entry.mirror_x:
                working_cap = mirror(cap, Plane.YZ)  # type: ignore[assignment]
                if choc_stem is not None:
                    working_stem = mirror(choc_stem, Plane.YZ)  # type: ignore[assignment]
            else:
                working_cap = cap
                working_stem = choc_stem

            def make_text_piece(
                char: str,
                font: str,
                size: float,
                x_off: float,
                y_off: float,
                bold: float,
            ) -> Part:
                """Build one legend piece anchored to its own local surface.

                Each piece is placed 0.4mm below the lowest surface point
                under its OWN footprint, keeping the carve depth uniform so
                enclosed counters (O, @, ...) never pierce the top wall and
                detach as islands.
                """
                if settings.baseline_align:
                    # Keep the font baseline so punctuation stays where it
                    # belongs (' high, _ low); capitals end up centered
                    y_off -= settings.cap_height_ratio * size / 2
                pln = Plane(
                    origin=text_pln.origin
                    + text_pln.x_dir * x_off
                    + text_pln.y_dir * y_off,
                    z_dir=text_pln.z_dir,
                    x_dir=text_pln.x_dir,
                )
                with BuildSketch(pln) as bs:
                    Text(
                        char,
                        font_size=size,
                        font=font,
                        align=(
                            Align.CENTER,
                            Align.NONE if settings.baseline_align else Align.CENTER,
                        ),
                    )
                base = bs.sketch

                def by_offset(amount: float) -> Sketch:
                    return offset(base, amount=amount, kind=Kind.ARC)  # type: ignore[return-value]

                def by_dilation(amount: float) -> Sketch:
                    # Some outlines (e.g. zeta's curl) break 2D offset -
                    # dilate by unioning shifted copies instead
                    sketch = base
                    for i in range(8):
                        a = i * math.pi / 4
                        sketch = sketch + Pos(
                            amount * math.cos(a), amount * math.sin(a)
                        ) * base
                    # complex outlines can degrade the fuse chain into a
                    # bare ShapeList/Compound - rebuild a proper Sketch so
                    # extrude() sees clean planar faces
                    return Sketch(sketch.faces())

                # The 2D offset can raise or silently produce an invalid
                # outline (e.g. Bahnschrift '6'), so every variant is checked
                attempts = []
                if bold:
                    attempts += [
                        ("offset", lambda: by_offset(bold)),
                        ("union dilation", lambda: by_dilation(bold)),
                    ]
                attempts.append(("plain outline", lambda: base))
                # Some glyphs are invalid as drawn (e.g. Bahnschrift '9'); a
                # dilation far below print resolution repairs them
                attempts += [
                    ("repaired outline", lambda: by_dilation(0.01)),
                    ("repaired outline", lambda: by_offset(0.01)),
                ]
                solid = None
                for label, make_sketch in attempts:
                    try:
                        candidate = extrude(
                            make_sketch(), amount=6, dir=text_pln.z_dir, both=False
                        )
                    except Exception:
                        continue
                    if candidate.is_valid and candidate.volume > 0:
                        solid = candidate
                        if label != attempts[0][0]:
                            print(f"    ('{char}' drawn via {label})")
                        break
                if solid is None:
                    raise RuntimeError(f"no valid outline for '{char}' in {font}")
                footprint = solid.bounding_box()
                surface_z = probe_top_surface_z(working_cap, bbox, footprint)
                if surface_z is not None:
                    # Bottom just below the deepest carve under this piece;
                    # the depth bound below trims it to follow the surface
                    dz = (
                        surface_z - settings.max_carve_depth - 0.2
                    ) - footprint.min.Z
                else:
                    local_z = find_legend_plane_z(
                        working_cap, bbox, footprint=footprint
                    )
                    dz = local_z - legend_z
                if abs(dz) > 1e-6:
                    solid = Pos(0, 0, dz) * solid
                return solid  # type: ignore[return-value]

            # One tool solid per slot, so each slot becomes its own 3MF part.
            # Bound the carve depth: subtract a downshifted copy of the cap
            # so the cut follows the top surface and never goes deeper than
            # max_carve_depth - enclosed glyph counters (O, @, &) would
            # otherwise pierce the wall on curved tops and detach as islands
            depth_stop = Pos(0, 0, -settings.max_carve_depth) * working_cap
            tools: list[tuple[int, Part]] = []
            boxes: list[tuple[int, BoundBox]] = []
            try:
                for index, text, font, size, x_off, y_off, bold in slots:
                    piece = make_text_piece(text, font, size, x_off, y_off, bold)
                    bb = piece.bounding_box()
                    if (
                        bb.min.X < bbox.min.X + 1.0
                        or bb.max.X > bbox.max.X - 1.0
                        or bb.min.Y < bbox.min.Y + 1.0
                        or bb.max.Y > bbox.max.Y - 1.0
                    ):
                        print(
                            f"    WARNING: {SLOTS[index - 1]} legend '{text}' "
                            "reaches the cap edge"
                        )
                    for other_index, other in boxes:
                        if (
                            bb.min.X < other.max.X
                            and other.min.X < bb.max.X
                            and bb.min.Y < other.max.Y
                            and other.min.Y < bb.max.Y
                        ):
                            print(
                                f"    WARNING: {SLOTS[index - 1]} and "
                                f"{SLOTS[other_index - 1]} legends overlap"
                            )
                    boxes.append((index, bb))
                    bounded = piece - depth_stop
                    if solids_of(bounded):
                        piece = bounded  # type: ignore[assignment]
                    else:
                        print(
                            "    WARNING: depth bounding failed - using full-depth carve"
                        )
                    tools.append((index, piece))
            except Exception as e:
                print(f"    ERROR: could not build legend '{legend_desc}': {e}")
                failed.append(str(key_name))
                continue

            print("    Boolean subtract...")
            carved = carve_legends(working_cap, tools)
            if carved is None:
                print(f"    ERROR: booleans failed for '{legend_desc}' - skipping")
                failed.append(str(key_name))
                continue
            cut_solids, legends = carved
            hole_cap: Solid = max(cut_solids, key=lambda s: s.volume)
            dropped = [s for s in cut_solids if s is not hole_cap]
            if dropped:
                vols = [round(s.volume, 3) for s in dropped]
                print(
                    f"    WARNING: dropped {len(dropped)} island solids {vols} "
                    f"for '{legend_desc}' - possible hole in a glyph counter!"
                )

            # Mesher exports one 3MF object per solid and reads label/color
            # from each solid - booleans and mirror() return compounds, so
            # stamp every solid or parts come out unnamed and uncolored
            hole_solids: list[Solid] = list(hole_cap.solids())
            for s in hole_solids:
                s.color = Color("gray")
                s.label = "cap body"
            for index, solids in legends.items():
                for s in solids:
                    s.color = Color(SLOT_COLORS[index - 1])
                    s.label = f"legend_{index}"
            stem_solids: list[Solid] = []
            if working_stem is not None:
                stem_solids = list(working_stem.solids())
                for s in stem_solids:
                    s.color = Color("gray")
                    s.label = "stem"

            if show is not None:
                try:
                    all_legends = [s for solids in legends.values() for s in solids]
                    show([*hole_solids, *all_legends, *stem_solids])
                except Exception as e:
                    print(f"    (viewer unavailable, skipping preview: {e})")
            try:
                m: Mesher = Mesher(unit=Unit.MM)
                m.add_shape(hole_solids, linear_deflection=0.06, angular_deflection=0.3)
                for index in sorted(legends):
                    m.add_shape(
                        legends[index], linear_deflection=0.01, angular_deflection=0.05
                    )
                if stem_solids:
                    m.add_shape(
                        stem_solids, linear_deflection=0.06, angular_deflection=0.3
                    )
                filename = build_filename(entry, row_name)
                m.write(filename)
                bambuify_3mf(filename, part_extruders)
                written.append(filename)
                print(f"    Wrote {filename}")
            except RuntimeError as e:
                print(f"    ERROR: Failed to create mesh for '{legend_desc}': {e}")
                failed.append(str(key_name))

    print(f"Done: {len(written)} keycaps written, {len(failed)} failed")
    if failed:
        print("Failed keys: " + ", ".join(failed))
    if args.plate and written:
        write_plate_3mf(sorted(written), args.plate, part_extruders)
        print(f"Plate written: {args.plate} ({len(written)} keycaps)")


if __name__ == "__main__":
    main()
