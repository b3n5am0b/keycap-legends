# SPDX-License-Identifier: MIT
"""Per-key Excel (.xlsx) table for the keycap legends.

The general config (settings, step_files) stays in the JSON/TOML file; the
table holds one row per key and replaces that file's `legends` section. Both
are merged into one temp JSON that `config.load_config` reads, so the rest of
the program is unchanged.

Sheet "keys", columns:
  name | primary | secondary | tertiary | <slot>_x_offset | <slot>_y_offset ...
  | <slot>_font | <slot>_font_size ... | mirror_x | row
`row` is the row group (step_files key, e.g. mbk_1u). Empty cell = not set
(falls back to [settings]). Any LegendEntry field may be used as a column;
other columns (e.g. an "ok" checklist or notes) are ignored with a notice.

CLI:
  uv run utils/config_table.py to-xlsx CONFIG.json OUT.xlsx      (export legends)
  uv run utils/config_table.py to-json CONFIG.json IN.xlsx OUT.json  (merge)
"""

import json
import sys
import tempfile
import tomllib
from dataclasses import fields
from pathlib import Path
from typing import Any

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font

# Allow running as a script (utils/config_table.py) as well as importing
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from models import SLOTS, LegendEntry  # noqa: E402

SHEET = "keys"
ROW_COLUMN = "row"
COLUMNS: list[str] = [
    "name",
    *SLOTS,
    *(f"{slot}_{axis}_offset" for slot in SLOTS for axis in ("x", "y")),
    *(f"{slot}_{prop}" for slot in SLOTS for prop in ("font", "font_size")),
    "mirror_x",
    ROW_COLUMN,
]


def _field_kinds() -> dict[str, str]:
    """Map each LegendEntry field to 'str', 'bool', 'float' (or 'any')."""
    kinds: dict[str, str] = {}
    for f in fields(LegendEntry):
        text = str(f.type)
        kinds[f.name] = next(
            (k for k in ("bool", "str", "float") if k in text), "any"
        )
    return kinds


def _coerce(value: Any, kind: str) -> Any:
    """Convert an Excel cell value to the LegendEntry field's type."""
    if kind == "str":
        if isinstance(value, float) and value.is_integer():
            return str(int(value))
        return str(value)
    if kind == "bool":
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in ("true", "yes", "1", "x"):
                return True
            if lowered in ("false", "no", "0"):
                return False
            raise ValueError(f"not a boolean: {value!r}")
        return bool(value)
    if kind == "float":
        return float(value)
    return value


def _load_base(config_path: Path | str) -> dict[str, Any]:
    path = Path(config_path)
    if path.suffix.lower() == ".json":
        return json.loads(path.read_text(encoding="utf-8"))
    with path.open("rb") as f:
        return tomllib.load(f)


def table_to_legends(xlsx_path: Path | str) -> dict[str, list[dict[str, Any]]]:
    """Read the per-key table into the `legends` structure of the config."""
    wb = load_workbook(xlsx_path, data_only=True, read_only=True)
    ws = wb[SHEET] if SHEET in wb.sheetnames else wb.worksheets[0]
    rows = ws.iter_rows(values_only=True)
    header = [str(h).strip() if h is not None else None for h in next(rows, [])]
    if ROW_COLUMN not in header:
        raise ValueError(f"{xlsx_path}: missing '{ROW_COLUMN}' column (row group)")
    kinds = _field_kinds()
    # Columns that are not LegendEntry fields (notes, checklists, ...) are
    # ignored; listed so a typo in a real column name doesn't go unnoticed
    ignored = [h for h in header if h and h != ROW_COLUMN and h not in kinds]
    if ignored:
        print(f"Config table: ignoring non-legend column(s): {', '.join(ignored)}")
    header = [h if h not in ignored else None for h in header]

    legends: dict[str, list[dict[str, Any]]] = {}
    for line, values in enumerate(rows, start=2):
        record = {
            key: value
            for key, value in zip(header, values)
            if key and value is not None and value != ""
        }
        if not record:
            continue
        group = record.pop(ROW_COLUMN, None)
        if group is None:
            raise ValueError(f"{xlsx_path}: line {line} has no '{ROW_COLUMN}'")
        entry = {k: _coerce(v, kinds[k]) for k, v in record.items()}
        legends.setdefault(str(group), []).append(entry)
    wb.close()
    return legends


def merge_config_table(
    config_path: Path | str,
    xlsx_path: Path | str,
    json_path: Path | str | None = None,
) -> Path:
    """Write the general config with its legends replaced by the table.

    Returns the JSON path (a temp file unless `json_path` is given), ready
    for `load_config()`.
    """
    data = _load_base(config_path)
    data["legends"] = table_to_legends(xlsx_path)
    if json_path is None:
        with tempfile.NamedTemporaryFile(
            prefix=f"{Path(xlsx_path).stem}_", suffix=".json", delete=False
        ) as tmp:
            json_path = tmp.name
    json_path = Path(json_path)
    json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return json_path


def legends_to_table(config_path: Path | str, xlsx_path: Path | str) -> None:
    """Export the legends of a JSON/TOML config as a per-key table."""
    data = _load_base(config_path)
    records = [
        {**entry, ROW_COLUMN: group}
        for group, entries in data.get("legends", {}).items()
        for entry in entries
    ]
    extra = sorted({k for r in records for k in r} - set(COLUMNS))
    columns = [c for c in COLUMNS if any(c in r for r in records)] + extra

    wb = Workbook()
    ws = wb.active
    ws.title = SHEET
    ws.append(columns)
    for cell in ws[1]:
        cell.font = Font(bold=True)
    for record in records:
        ws.append([record.get(c) for c in columns])
        # Store glyphs/names as text so "7" stays a string
        for cell in ws[ws.max_row]:
            if isinstance(cell.value, str):
                cell.number_format = "@"
    ws.freeze_panes = "B2"
    ws.auto_filter.ref = ws.dimensions
    for col in ws.columns:
        width = max(len(str(c.value)) if c.value is not None else 0 for c in col)
        ws.column_dimensions[col[0].column_letter].width = min(max(width + 2, 6), 40)
    wb.save(xlsx_path)


if __name__ == "__main__":
    args = sys.argv[1:]
    if args[:1] == ["to-xlsx"] and len(args) == 3:
        legends_to_table(args[1], args[2])
        print(f"Wrote {args[2]}")
    elif args[:1] == ["to-json"] and len(args) == 4:
        merge_config_table(args[1], args[2], args[3])
        print(f"Wrote {args[3]}")
    else:
        raise SystemExit(
            "usage: config_table.py to-xlsx CONFIG OUT.xlsx\n"
            "       config_table.py to-json CONFIG IN.xlsx OUT.json"
        )
