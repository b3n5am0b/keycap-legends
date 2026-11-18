import numpy as np
from build123d import import_step

cap = import_step("assets/my-kailh-v0.0.2.step")
bb = cap.bounding_box()
zmin = bb.min.Z
print("bbox size", [round(v,3) for v in (bb.size.X, bb.size.Y, bb.size.Z)], "zmin", round(zmin,3))

faces = cap.faces()
print(f"{len(faces)} faces. Largest 12 by area:")
rows = []
for f in faces:
    c = f.center()
    try:
        n = f.normal_at()
        nz = round(n.Z, 2)
    except Exception:
        nz = None
    rows.append((f.area, round(c.Z - zmin, 2), nz,
                 round(c.X, 2), round(c.Y, 2)))
rows.sort(reverse=True)
print(f"{'area':>8} {'cZ(from bottom)':>16} {'nZ':>6} {'cX':>7} {'cY':>7}")
for a, cz, nz, cx, cy in rows[:12]:
    print(f"{a:8.2f} {cz:16.2f} {str(nz):>6} {cx:7.2f} {cy:7.2f}")
