# SPDX-License-Identifier: MIT

from dataclasses import dataclass, field

# Legend slots in part order: slot N is exported as 3MF part "legend_N".
SLOTS: tuple[str, ...] = ("primary", "secondary", "tertiary", "quaternary")


@dataclass
class LegendEntry:
    """Configuration for a single keycap legend."""

    primary: str | None = None
    secondary: str | None = None
    name: str | None = None
    mirror_x: bool = False
    primary_font: str | None = None
    primary_font_size: float | None = None
    primary_x_offset: float | None = None
    primary_y_offset: float | None = None
    secondary_font_size: float | None = None
    secondary_x_offset: float | None = None
    secondary_y_offset: float | None = None
    secondary_font: str | None = None
    tertiary: str | None = None
    tertiary_font: str | None = None
    tertiary_font_size: float | None = None
    tertiary_x_offset: float | None = None
    tertiary_y_offset: float | None = None
    quaternary: str | None = None
    quaternary_font: str | None = None
    quaternary_font_size: float | None = None
    quaternary_x_offset: float | None = None
    quaternary_y_offset: float | None = None


@dataclass
class StepFileConfig:
    """Configuration for a STEP file source."""

    path: str
    rotation: int = 0
    has_stem: bool = False
    stl: str | None = None


@dataclass
class LegendSettings:
    """Global settings for legend generation."""

    font: str = "Rajdhani"
    primary_font_size: float = 8
    secondary_font_size: float = 6
    tertiary_font_size: float = 5
    tertiary_x_offset: float = -5.0
    tertiary_y_offset: float = 0.0
    quaternary_font_size: float = 3.5
    quaternary_x_offset: float = -3.3
    quaternary_y_offset: float = -3.3
    secondary_x_offset: float = -3.3
    secondary_y_offset: float = -3.3
    primary_x_offset: float = 0.0
    primary_y_offset: float = 0.0
    bold_offset: float = 0.0
    # Bold offset for the other (small) slots; too much closes the gaps
    # in glyphs like = or "
    small_bold_offset: float = 0.0
    max_carve_depth: float = 0.8
    # Align legends on the font baseline instead of centering each glyph's
    # outline; cap_height_ratio (capital height / font size) centers capitals
    baseline_align: bool = False
    cap_height_ratio: float = 0.7
    # A key with only one legend gets it centered, ignoring the slot offset
    center_single_legend: bool = True
    body_filament: int = 1
    legend_filament: int = 2
    stem_filament: int = 1
    # Filament for the cradle object (the tiled keycapsupport) on a cradle plate
    cradle_filament: int = 1
    # Per-slot filament (primary..quaternary); None falls back to legend_filament
    legend_1_filament: int | None = None
    legend_2_filament: int | None = None
    legend_3_filament: int | None = None
    legend_4_filament: int | None = None

    def slot_filament(self, index: int) -> int:
        """Filament slot for legend part `index` (1-based)."""
        value = getattr(self, f"legend_{index}_filament")
        return self.legend_filament if value is None else value


@dataclass
class Config:
    """Complete configuration for keycap generation."""

    settings: LegendSettings = field(default_factory=LegendSettings)
    step_files: dict[str, StepFileConfig] = field(default_factory=dict)
    legends: dict[str, list[LegendEntry]] = field(default_factory=dict)
