# Print config: Chocofi keycaps on a Bambu Lab A1 + AMS

Slicer settings for `results/chocofi_plate.3mf` (output of `workflow.md`) on a
**Bambu Lab A1** with the **AMS Lite** (the enclosed AMS works too, via a hub).

Two complete configs follow: one for the **0.4 mm** nozzle (faster, the default
choice) and one for the **0.2 mm** nozzle (sharper legends, much slower). Both
are built around the same fact: the colors exist only in the **top 0.4 mm**
of each cap (`max_carve_depth = 0.4`), and the cap prints **upright, stem down**,
so each legend resolves into clean horizontal top-layer regions.

This set uses **two filaments only** — one body color and a single legend color
shared by all three layers (`legend_1/2/3_filament = 2`). Combined with the
shallow 0.4 mm carve, that keeps color changes to ~1 per top layer across just a
few layers, so purge/waste is minimal.

## Shared essentials (apply to both configs)

- **Plate fits as-is.** The plate is centered on a 256×256 bed — exactly the A1
  build area. Don't rescale or auto-arrange. Keep all 36 caps on one plate:
  color-change purge is front-loaded into the top layers and amortizes across
  the whole plate.
- **Do not auto-orient.** Upright (stem down) is what makes the multicolor work.
- **Print sequence: By layer.** Required for color changes. Never "by object".
- **No ironing.** Ironing drags the nozzle across the multicolor top and smears
  the legends together.
- **AMS slot order:**

  | Slot | Part | Role |
  |---|---|---|
  | 1 | `cap body` | body color |
  | 2 | `legend_1` | Base layer |
  | 3 | `legend_2` | Num layer |
  | 4 | `legend_3` | Sym layer |

- **Filament:** PLA Basic or Matte. Avoid Silk PLA — it bleeds between colors and
  bonds poorly. Use high contrast between body and legends.

## Config A — 0.4 mm nozzle (default)

Start from process preset `0.12mm Fine @BBL A1`, filament PLA Basic ×4.

### Quality
| Setting | Value |
|---|---|
| Layer height | 0.12 mm (use 0.10 mm for finer legends) |
| First layer height | 0.2 mm |
| Line width — default / wall / top | 0.42 mm |
| First layer line width | 0.5 mm |
| Seam position | Back |
| Precise wall / Precise Z height | On |
| Detect thin wall | On |
| Ironing | Off |

### Walls / top / bottom
| Setting | Value |
|---|---|
| Wall loops | 3 |
| **Top shell thickness** | **1.0 mm** (must exceed the 0.6 mm carve — see callouts) |
| Top surface pattern | Monotonic |
| Bottom shell layers | 3 |
| Sparse infill | 15%, Grid |

### Speed
| Setting | Value |
|---|---|
| Outer wall | 120 mm/s |
| Inner wall | 200 mm/s |
| Top/bottom surface | 100 mm/s |
| Small perimeters | 40 mm/s (the legends) |
| Sparse infill | 250 mm/s |
| First layer | 30 mm/s |
| Travel | 300 mm/s, Z-hop 0.4 mm |
| Filament max volumetric speed | ~12 mm³/s |

### Supports
| Setting | Value |
|---|---|
| Enable | On, type Normal (auto) |
| Support on | Everywhere |
| Top Z distance (gap) | 0.2 mm |
| Top interface layers | 3 |
| Interface spacing | 0.2 mm |
| Threshold angle | 30° |
| Pattern | Rectilinear |

### Adhesion
| Setting | Value |
|---|---|
| Brim type | Outer brim only |
| Brim width | 5 mm |
| Brim-object gap | 0.1 mm |

### Multicolor / flushing
| Setting | Value |
|---|---|
| Flush into infill / object / support | On / On / On |
| Prime/wipe tower | On |
| Flush volumes | Calibrated; trim for similar colors, keep high for dark→light |

### Filament (PLA)
| Setting | Value |
|---|---|
| Nozzle temp | 220 °C first layer / 210 °C rest |
| Bed (textured PEI) | 55 °C |
| Part cooling fan | 100% after layer 2 |
| Min layer time | 8 s |

## Config B — 0.2 mm nozzle (fine legends)

Start from process preset `0.08mm Extra Fine @BBL A1 (0.2 nozzle)`, printer set
to the **0.2 mm nozzle**, filament PLA Basic ×4.

### Quality
| Setting | Value |
|---|---|
| Layer height | 0.08 mm |
| First layer height | 0.1 mm |
| Line width — default / wall / top | 0.2 mm |
| First layer line width | 0.3 mm |
| Seam position | Back |
| Precise wall / Precise Z height | On |
| Detect thin wall | On |
| Ironing | Off |

### Walls / top / bottom
| Setting | Value |
|---|---|
| Wall loops | 3 |
| **Top shell thickness** | **1.0 mm** (must exceed the 0.6 mm carve — see callouts) |
| Top surface pattern | Monotonic |
| Bottom shell layers | 3 |
| Sparse infill | 15%, Grid |

### Speed (keep low — the 0.2 nozzle has a small flow ceiling)
| Setting | Value |
|---|---|
| Outer wall | 50 mm/s |
| Inner wall | 100 mm/s |
| Top/bottom surface | 40 mm/s |
| Small perimeters | 25 mm/s (the legends) |
| Sparse infill | 120 mm/s |
| First layer | 25 mm/s |
| Travel | 200 mm/s, Z-hop 0.4 mm |
| Filament max volumetric speed | ~3 mm³/s (the real speed limiter) |

### Supports
| Setting | Value |
|---|---|
| Enable | On, type Normal (auto) |
| Support on | Everywhere |
| Top Z distance (gap) | 0.2 mm |
| Top interface layers | 4 |
| Interface spacing | 0.2 mm |
| Threshold angle | 30° |
| Pattern | Rectilinear |

### Adhesion
| Setting | Value |
|---|---|
| Brim type | Outer brim only |
| Brim width | 5 mm |
| Brim-object gap | 0.1 mm |

### Multicolor / flushing
| Setting | Value |
|---|---|
| Flush into infill / object / support | On / On / On |
| Prime/wipe tower | On |
| Flush volumes | Calibrated; trim for similar colors, keep high for dark→light |

### Filament (PLA)
| Setting | Value |
|---|---|
| Nozzle temp | 220 °C first layer / 210 °C rest |
| Bed (textured PEI) | 55 °C |
| Part cooling fan | 100% after layer 2 |
| Min layer time | 8 s |

## Which to use

| | 0.4 mm | 0.2 mm |
|---|---|---|
| Legend sharpness | Good | Best (fine strokes, small glyphs) |
| Print time (36 caps + supports) | Several hours | ~A day |
| Flow headroom | High | Low — speeds are flow-capped |
| Best for | Everyday sets, first full run | Showcase sets, tiny Num/Sym legends |

## Geometry-specific callouts (both configs)

1. **Top shell ≥ 1.0 mm is the setting that matters most.** The legends live in
   the top 0.6 mm. If the solid top shell is thinner than the carve depth, the
   color boundaries fall into sparse infill and the legends print ragged or
   translucent. 1.0 mm keeps the whole colored zone solid.
2. **Brim is not optional.** The stem (~7×3 mm) is the only bed contact per cap;
   without a brim the caps lift or tip.
3. **Supports "everywhere".** The hollow underside and the skirt overhang above
   the stem need support; "on build plate only" won't reach them.

## Pre-slice checklist

1. Open `results/chocofi_plate.3mf`; confirm 36 objects, each with parts
   `cap body`, `legend_1`, `legend_2`, `legend_3` on filaments 1–4.
2. Load the 4 filaments in slot order (body, Base, Num, Sym).
3. Apply the config for your nozzle.
4. Slice, then scroll the layer slider: color changes must appear **only in the
   top ~0.6 mm**, with a single-color body below. If colors appear lower, stop
   and recheck the part/filament assignment.
5. Test one cap first (`uv run main.py --config chocofi/chocofi.json --only P02_E`)
   to validate stem fit, support removal, and legend sharpness before the full
   plate.
