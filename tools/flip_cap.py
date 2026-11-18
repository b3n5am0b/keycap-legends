# SPDX-License-Identifier: MIT
"""Flip a keycap STEP 180 degrees so its legend/typing face points up (+Z).

main.py carves the legend into the top (max Z) face. A cap modeled stem-up with
the typing face at Zmin (e.g. for upside-down printing) must therefore be turned
over first. This is a proper 180 deg rotation about X (no mirroring), so the
cap's chirality is preserved.

    uv run tools/flip_cap.py assets/my-kailh-v0.0.2.step assets/my-kailh-v0.0.2_flipped.step
"""

import argparse
from pathlib import Path

from build123d import Rotation, export_step, import_step


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("src", type=Path, help="source STEP (typing face at Zmin)")
    parser.add_argument("dst", type=Path, help="output STEP (typing face up)")
    args = parser.parse_args()

    cap = import_step(str(args.src))
    flipped = Rotation(180, 0, 0) * cap
    export_step(flipped, str(args.dst))
    print(f"Wrote {args.dst} (flipped 180deg about X)")


if __name__ == "__main__":
    main()
