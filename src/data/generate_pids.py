"""Draw synthetic P&IDs as vector PDFs (plus PNG previews) with ISA-5.1 style tags and symbols.

Every drawing is invented. The generator writes the true content of each drawing to
data/raw/ground_truth/<drawing>.json so the reader can be scored.

Drawing conventions used (documented in the README):
  equipment  T tank, V drum, C column (rectangles); P pump, E exchanger (circles); K compressor (trapezoid)
             tag written inside the symbol, e.g. V-301, P-302A
  lines      thick solid polylines, arrowhead at the downstream end, line number above, e.g. 4"-P-3005
  valves     control valve = bowtie with actuator, tag above (FV-310); check valve = triangle + bar, tag below (NRV-312);
             relief valve on top of the equipment with tag (PSV-311)
  instruments  circle ("bubble"), function letters on top (LIC), loop number below (310), joined to the
               measured equipment or line by a thin dashed signal line
About a third of the drawings are "messy": some signal lines are missing and some labels are nudged,
so the reader has to fall back on proximity.

Usage: python -m src.data.generate_pids [--n 30] [--n-hard 20] [--seed 42]
"""
from __future__ import annotations

import argparse
import json
import random
import shutil

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, FancyBboxPatch, Polygon, Rectangle

from src.utils.paths import DATA_RAW, DATA_SAMPLE  # noqa: E402

OUT = DATA_RAW
TRAINS = [
    ["T", "P", "E", "V", "P", "T"],
    ["V", "P", "E", "C", "P", "T"],
    ["T", "P", "V", "K", "V"],
    ["V", "P", "E", "V", "P", "T"],
    ["T", "P", "C", "P", "E", "T"],
    ["V", "K", "E", "V", "P"],
]
SIZE = {"T": (2.6, 2.6), "V": (1.6, 2.8), "C": (1.3, 5.0), "P": (1.1, 1.1), "E": (1.4, 1.4), "K": (1.8, 1.4)}
PROCESS_LW, SIGNAL_LW = 2.0, 0.6
CY = 8.5


class Drawing:
    def __init__(self, ax, rng, unit, messy, hard=False):
        self.ax, self.rng, self.unit, self.messy, self.hard = ax, rng, unit, messy or hard, hard
        self.jit = 0.9 if hard else 0.3
        self.loop = unit * 100 + 10
        self.truth = dict(equipment=[], lines=[], instruments=[], relief_valves=[])

    def next_loop(self):
        self.loop += 1
        return self.loop

    # ---------- symbols ----------
    def equipment(self, kind, tag, cx):
        w, h = SIZE[kind]
        x0, y0 = cx - w / 2, CY - h / 2
        if kind in ("P", "E"):
            self.ax.add_patch(Circle((cx, CY), w / 2, fill=False, lw=1.4))
        elif kind == "V":
            self.ax.add_patch(FancyBboxPatch((x0, y0), w, h, boxstyle="round,pad=0,rounding_size=0.5", fill=False, lw=1.4))
        elif kind == "K":
            self.ax.add_patch(Polygon([(x0, y0 + 0.2), (x0 + w, y0), (x0 + w, y0 + h), (x0, y0 + h - 0.2)],
                                      closed=True, fill=False, lw=1.4))
        else:
            self.ax.add_patch(Rectangle((x0, y0), w, h, fill=False, lw=1.4))
        self.ax.text(cx, CY, tag, ha="center", va="center", fontsize=7)
        self.truth["equipment"].append(dict(tag=tag, type=kind))
        return dict(tag=tag, kind=kind, cx=cx, x0=x0, x1=x0 + w, y0=y0, y1=y0 + h)

    def bubble(self, x, y, letters, number, attach_pt, attached_to):
        self.ax.add_patch(Circle((x, y), 0.42, fill=False, lw=0.9))
        self.ax.text(x, y + 0.13, letters, ha="center", va="center", fontsize=6)
        self.ax.text(x, y - 0.17, str(number), ha="center", va="center", fontsize=6)
        drop = self.messy and self.rng.random() < (0.7 if self.hard else 0.35)
        if not drop:
            sx, sy = attach_pt
            d = ((sx - x) ** 2 + (sy - y) ** 2) ** 0.5
            ex, ey = x + (sx - x) / d * 0.42, y + (sy - y) / d * 0.42  # start at the bubble's edge
            self.ax.plot([ex, sx], [ey, sy], lw=SIGNAL_LW, ls=(0, (3, 2)), color="k")
        self.truth["instruments"].append(dict(tag=f"{letters}-{number}", attached_to=attached_to,
                                              signal_line_drawn=not drop))

    def control_valve(self, x, y, tag):
        s = 0.28
        self.ax.add_patch(Polygon([(x - s, y + s * 0.7), (x - s, y - s * 0.7), (x, y)], closed=True, fill=False, lw=1))
        self.ax.add_patch(Polygon([(x + s, y + s * 0.7), (x + s, y - s * 0.7), (x, y)], closed=True, fill=False, lw=1))
        self.ax.plot([x, x], [y, y + 0.45], lw=0.9, color="k")
        self.ax.add_patch(Polygon([(x - 0.22, y + 0.45), (x + 0.22, y + 0.45), (x, y + 0.65)], closed=True, fill=False, lw=0.9))
        dx = self.rng.uniform(-self.jit, self.jit) if self.messy else 0
        self.ax.text(x + dx, y + 0.9, tag, ha="center", va="center", fontsize=6)

    def check_valve(self, x, y, tag):
        self.ax.add_patch(Polygon([(x - 0.22, y + 0.2), (x - 0.22, y - 0.2), (x + 0.12, y)], closed=True, fill=False, lw=1))
        self.ax.plot([x + 0.14, x + 0.14], [y - 0.22, y + 0.22], lw=1, color="k")
        self.ax.text(x, y - 0.5, tag, ha="center", va="center", fontsize=6)

    def relief_valve(self, eq, tag):
        x, y = eq["x1"] - 0.3, eq["y1"]
        self.ax.plot([x, x], [y, y + 0.35], lw=1.2, color="k")
        self.ax.add_patch(Polygon([(x - 0.2, y + 0.35), (x + 0.2, y + 0.35), (x, y + 0.6)], closed=True, fill=False, lw=1))
        self.ax.text(eq["cx"] + 1.55, y + 0.4, tag, ha="left", va="center", fontsize=6)
        self.truth["relief_valves"].append(dict(tag=tag, equipment=eq["tag"]))

    def process_line(self, pts, line_no):
        no_arrow = self.hard and self.rng.random() < 0.2
        drawn = list(reversed(pts)) if no_arrow and self.rng.random() < 0.5 else pts  # path order says nothing
        xs, ys = zip(*drawn)
        self.ax.plot(xs, ys, lw=PROCESS_LW, color="k", solid_capstyle="butt")
        if no_arrow:
            self.truth.setdefault("lines_without_arrow", []).append(line_no)
            return
        (x1, y1), (x2, y2) = pts[-2], pts[-1]
        ux, uy = (x2 - x1), (y2 - y1)
        n = (ux ** 2 + uy ** 2) ** 0.5
        ux, uy = ux / n, uy / n
        tip, base = (x2, y2), (x2 - ux * 0.35, y2 - uy * 0.35)
        self.ax.add_patch(Polygon([tip, (base[0] - uy * 0.15, base[1] + ux * 0.15),
                                   (base[0] + uy * 0.15, base[1] - ux * 0.15)], closed=True, fill=True, color="k"))

    # ---------- connections ----------
    def outlet(self, e):
        return ("bottom", (e["cx"], e["y0"])) if e["kind"] in ("T", "V", "C") else ("side", (e["x1"], CY))

    def inlet(self, e):
        return (e["x0"], CY + 0.8) if e["kind"] in ("T", "V", "C") else (e["x0"], CY)

    def connect(self, a, b, k):
        kind, (sx, sy) = self.outlet(a)
        ex, ey = self.inlet(b)
        xm = (a["x1"] + b["x0"]) / 2
        if kind == "bottom":
            low = a["y0"] - 0.9
            pts = [(sx, sy), (sx, low), (xm, low), (xm, ey), (ex, ey)]
        else:
            pts = [(sx, sy), (xm, sy), (xm, ey), (ex, ey)]
        line_no = f'{self.rng.choice([2, 3, 4, 6, 8])}"-P-{self.unit}{k:03d}'
        self.process_line(pts, line_no)
        # The longest horizontal segment carries the valves, line number and line instruments.
        segs = [(pts[i], pts[i + 1]) for i in range(len(pts) - 1) if pts[i][1] == pts[i + 1][1]]
        (hx1, hy), (hx2, _) = max(segs, key=lambda s: abs(s[1][0] - s[0][0]))
        L = hx2 - hx1
        at = lambda f: hx1 + L * f
        lx = at(0.78) + (self.rng.uniform(-self.jit, self.jit) if self.messy else 0)
        self.ax.text(lx, hy + 0.3, line_no, ha="center", va="bottom", fontsize=6)
        line = dict(line_no=line_no, from_=a["tag"], to=b["tag"], valves=[])
        cvx = at(0.5)
        if a["kind"] == "P" and self.rng.random() < 0.75:
            tag = f"NRV-{self.next_loop()}"
            self.check_valve(at(0.15), hy, tag)
            line["valves"].append(tag)
        if a["kind"] in ("T", "V", "C"):  # level control on the vessel outlet
            n = self.next_loop()
            self.control_valve(cvx, hy, f"LV-{n}")
            line["valves"].append(f"LV-{n}")
            a["level_loop"] = n
        elif a["kind"] == "P" and self.rng.random() < 0.6:  # flow control on pump discharge
            n = self.next_loop()
            self.control_valve(cvx, hy, f"FV-{n}")
            line["valves"].append(f"FV-{n}")
            self.bubble(cvx, hy - 1.4, "FIC", n, (cvx, hy), line_no)
            self.bubble(cvx - 1.0, hy - 1.4, "FT", n, (at(0.3), hy), line_no)
            if self.rng.random() < 0.5:
                self.bubble(cvx + 1.0, hy - 1.4, "FAL", n, (at(0.7), hy), line_no)
        elif a["kind"] == "E" and self.rng.random() < 0.7:
            n = self.next_loop()
            self.bubble(cvx, hy - 1.4, "TT", n, (cvx, hy), line_no)
            if self.rng.random() < 0.6:
                self.bubble(cvx + 1.0, hy - 1.4, "TAH", n, (at(0.7), hy), line_no)
        self.truth["lines"].append(dict(line_no=line_no, **{"from": a["tag"], "to": b["tag"]}, valves=line["valves"]))

    def vessel_instruments(self, e):
        bubbles = []
        n = e.get("level_loop") or self.next_loop()
        bubbles += [("LT", n), ("LIC", n)]
        if self.rng.random() < 0.8:
            bubbles.append(("LAH", n))
        if self.rng.random() < 0.5:
            bubbles.append(("LAL", n))
        if self.rng.random() < 0.5:
            bubbles.append(("LSHH", self.next_loop()))
        if self.rng.random() < 0.6 or e["kind"] == "C":
            m = self.next_loop()
            bubbles += [("PT", m)] + ([("PAH", m)] if self.rng.random() < 0.7 else [])
        if self.rng.random() < 0.3:
            bubbles.append(("TT", self.next_loop()))
        per_row = 3
        for i, (letters, num) in enumerate(bubbles):
            row, col = divmod(i, per_row)
            bx = e["cx"] + (col - 1) * 1.0 + (self.rng.uniform(-0.6, 0.6) if self.hard else 0)
            by = e["y1"] + 1.3 + row * 1.05
            ax_ = min(max(bx, e["x0"] + 0.15), e["x1"] - 0.15)
            self.bubble(bx, by, letters, num, (ax_, e["y1"]), e["tag"])


def draw_one(idx, rng, messy, hard=False, folder="drawings", prefix="SYN-PID"):
    unit = rng.randint(1, 9)
    train = rng.choice(TRAINS)[: rng.randint(4, 6)]
    if train[-1] == "P":
        train = train[:-1]
    fig, ax = plt.subplots(figsize=(22, 10))
    ax.set_xlim(0, 44)
    ax.set_ylim(0, 20)
    ax.axis("off")
    d = Drawing(ax, rng, unit, messy, hard)
    eqs, counts = [], {}
    for i, kind in enumerate(train):
        counts[kind] = counts.get(kind, 0) + 1
        tag = f"{kind}-{unit}{len(eqs) + 1:02d}" + ("A" if kind == "P" else "")
        eqs.append(d.equipment(kind, tag, 3.5 + i * 7.2))
    for k, (a, b) in enumerate(zip(eqs, eqs[1:]), start=1):
        d.connect(a, b, k)
    for e in eqs:
        if e["kind"] in ("T", "V", "C"):
            d.vessel_instruments(e)
            if rng.random() < 0.75:
                d.relief_valve(e, f"PSV-{d.next_loop()}")
        if e["kind"] == "K" and rng.random() < 0.8:
            n = d.next_loop()
            d.bubble(e["cx"], e["y1"] + 1.3, "VT", n, (e["cx"], e["y1"]), e["tag"])
            d.bubble(e["cx"] + 1.0, e["y1"] + 1.3, "VAH", n, (e["cx"] + 0.5, e["y1"]), e["tag"])
    ax.add_patch(Rectangle((32.5, 0.4), 11, 2.2, fill=False, lw=0.8))
    ax.text(33, 2.1, "SYNTHETIC P&ID - NOT A REAL PLANT", fontsize=7, va="center")
    ax.text(33, 1.4, f"DWG {prefix}-{idx:03d}   UNIT {unit}", fontsize=7, va="center")
    ax.text(33, 0.8, "Generated for a portfolio demo", fontsize=6, va="center")
    name = f"{prefix}-{idx:03d}"
    fig.savefig(OUT / folder / f"{name}.pdf")
    fig.savefig(OUT / folder / f"{name}.png", dpi=80)
    plt.close(fig)
    d.truth.update(drawing=name, unit=unit, messy=messy, hard=hard)
    (OUT / "ground_truth" / f"{name}.json").write_text(json.dumps(d.truth, indent=1))
    return d.truth


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=30)
    ap.add_argument("--n-hard", type=int, default=20)
    ap.add_argument("--seed", type=int, default=42)
    a = ap.parse_args()
    rng = random.Random(a.seed)
    for d in ("drawings", "drawings_hard", "ground_truth"):
        (OUT / d).mkdir(exist_ok=True)
        for f in (OUT / d).glob("SYN-*"):
            f.unlink()
    for label, n, kw in [("standard", a.n, dict()), ("hard", a.n_hard, dict(hard=True, folder="drawings_hard", prefix="SYN-HARD"))]:
        tot = dict(equipment=0, instruments=0, lines=0, relief_valves=0)
        for i in range(1, n + 1):
            t = draw_one(i, rng, messy=rng.random() < 0.35, **kw)
            for k in tot:
                tot[k] += len(t[k])
        print(f"{n} {label} drawings:", tot)
    for ext in ("pdf", "png"):
        shutil.copy(OUT / "drawings" / f"SYN-PID-007.{ext}", DATA_SAMPLE / f"SYN-PID-007.{ext}")
    shutil.copy(OUT / "ground_truth" / "SYN-PID-007.json", DATA_SAMPLE / "SYN-PID-007_truth.json")


if __name__ == "__main__":
    main()
