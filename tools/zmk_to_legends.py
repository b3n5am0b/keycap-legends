# SPDX-License-Identifier: MIT
"""Build a keycap-legends config from a ZMK keymap.

Reads the keymap YAML that keymap-drawer produces (``keymap parse``), takes
one legend per configured layer for every key position, and writes a JSON
config for main.py.

    uv run tools/zmk_to_legends.py chocofi/settings.toml
"""

import argparse
import json
import re
import tomllib
from pathlib import Path

import yaml

SLOTS = ("primary", "secondary", "tertiary", "quaternary")


def key_label(key: object) -> str:
    """Tap legend of one keymap-drawer key ('' for held/transparent/empty)."""
    if key is None:
        return ""
    if isinstance(key, dict):
        if key.get("type") in ("held", "trans", "ghost"):
            return ""
        key = key.get("t", key.get("tap", ""))
    return str(key).strip()


def build_config(settings_path: Path, glyphs_path: Path) -> dict:
    with settings_path.open("rb") as f:
        spec = tomllib.load(f)
    with glyphs_path.open("rb") as f:
        glyphs = tomllib.load(f)

    zmk = spec.pop("zmk")
    layer_names: list[str] = zmk["layers"]
    if len(layer_names) > len(SLOTS):
        raise SystemExit(f"At most {len(SLOTS)} layers can be printed on a key")
    keymap = yaml.safe_load(Path(zmk["keymap_yaml"]).read_text(encoding="utf-8"))
    layers = keymap["layers"]
    missing = [name for name in layer_names if name not in layers]
    if missing:
        raise SystemExit(
            f"Layer(s) {missing} not in keymap; available: {list(layers)}"
        )

    default_group: str = zmk["default_group"]
    group_of: dict[int, str] = {}
    for group, positions in zmk.get("groups", {}).items():
        for position in positions:
            group_of[position] = group

    symbol_font: str | None = glyphs.get("symbol_font")
    symbols = set(glyphs.get("symbols", ""))
    replace: dict[str, str] = glyphs.get("replace", {})
    scale: dict[str, float] = glyphs.get("scale", {})
    slot_sizes = {
        slot: spec.get("settings", {}).get(f"{slot}_font_size") for slot in SLOTS
    }

    key_count = len(layers[layer_names[0]])
    legends: dict[str, list[dict]] = {}
    for position in range(key_count):
        entry: dict[str, object] = {}
        base_label = ""
        for slot, layer_name in zip(SLOTS, layer_names):
            label = key_label(layers[layer_name][position])
            if slot == "primary":
                base_label = label
            text = replace.get(label, label)
            if not text:
                continue
            entry[slot] = text
            if symbol_font and any(ch in symbols for ch in text):
                entry[f"{slot}_font"] = symbol_font
            if label in scale:
                if slot_sizes[slot] is None:
                    raise SystemExit(
                        f"[scale] needs {slot}_font_size in [settings]"
                    )
                entry[f"{slot}_font_size"] = round(slot_sizes[slot] * scale[label], 3)
        if not entry:
            print(f"Position {position}: no legend on any layer, skipped")
            continue
        # Position-based name: unique file names, sorted in keymap order
        safe = re.sub(r"[^A-Za-z0-9]", "", base_label)
        entry["name"] = f"P{position:02d}" + (f"_{safe}" if safe else "")
        legends.setdefault(group_of.get(position, default_group), []).append(entry)

    for group in legends:
        if group not in spec.get("step_files", {}):
            raise SystemExit(f"Group '{group}' has no [step_files.{group}] entry")
    spec["legends"] = legends
    return spec


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("settings", type=Path, help="settings TOML with a [zmk] table")
    parser.add_argument(
        "--glyphs", type=Path, help="glyph table (default: glyphs.toml next to settings)"
    )
    parser.add_argument(
        "--out", type=Path, help="output JSON (default: <settings dir>/chocofi.json)"
    )
    args = parser.parse_args()

    glyphs = args.glyphs or args.settings.with_name("glyphs.toml")
    out = args.out or args.settings.with_name("chocofi.json")
    config = build_config(args.settings, glyphs)
    out.write_text(
        json.dumps(config, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    total = sum(len(entries) for entries in config["legends"].values())
    print(f"Wrote {out}: {total} keys in {len(config['legends'])} groups")


if __name__ == "__main__":
    main()
