# SPDX-License-Identifier: MIT

import json
import tomllib
from dataclasses import fields
from pathlib import Path
from typing import Any

from models import Config, LegendEntry, LegendSettings, StepFileConfig


def _build(cls: type, data: dict[str, Any], where: str) -> Any:
    """Build a dataclass from a dict, rejecting unknown keys."""
    known = {f.name for f in fields(cls)}
    unknown = sorted(set(data) - known)
    if unknown:
        raise ValueError(f"Unknown key(s) in {where}: {', '.join(unknown)}")
    return cls(**data)


def load_config(path: Path | str = "config.toml") -> Config:
    """Load configuration from a TOML or JSON file (chosen by extension)."""
    path = Path(path)
    if path.suffix.lower() == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
    else:
        with path.open("rb") as f:
            data = tomllib.load(f)

    settings = _build(LegendSettings, data.get("settings", {}), "[settings]")

    step_files: dict[str, StepFileConfig] = {}
    for name, step_data in data.get("step_files", {}).items():
        if isinstance(step_data, str):
            step_files[name] = StepFileConfig(path=step_data)
        else:
            step_files[name] = _build(
                StepFileConfig, step_data, f"[step_files.{name}]"
            )

    legends: dict[str, list[LegendEntry]] = {}
    for row_name, row_legends in data.get("legends", {}).items():
        legends[row_name] = [
            _build(LegendEntry, entry, f"[[legends.{row_name}]]")
            for entry in row_legends
        ]

    return Config(settings=settings, step_files=step_files, legends=legends)
