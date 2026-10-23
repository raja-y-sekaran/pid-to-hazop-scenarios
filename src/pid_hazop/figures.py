"""Overlay what the reader found on the drawing itself."""
from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.image as mpimg
import matplotlib.pyplot as plt
import numpy as np
import pdfplumber
from matplotlib.lines import Line2D
from matplotlib.patches import Rectangle

from .pipeline import DATA, DOCS
from .reader import read_pid

BLUE, ORANGE, AQUA, RED, INK, MUTED = "#2a78d6", "#eb6834", "#1baf7a", "#e34948", "#0b0b0b", "#52514e"
METHOD_COLOR = {"signal line": BLUE, "same loop": AQUA, "proximity": ORANGE}


def annotated(drawing="SYN-PID-002", folder="drawings", out="annotated_pid.png"):
    pdf = DATA / folder / f"{drawing}.pdf"
    m = read_pid(pdf)
    with pdfplumber.open(pdf) as p:
        W, H = p.pages[0].width, p.pages[0].height
    img = mpimg.imread(DATA / folder / f"{drawing}.png")
    sx, sy = img.shape[1] / W, img.shape[0] / H
    fig, ax = plt.subplots(figsize=(13, 6.2), dpi=150)
    ax.imshow(img, alpha=0.55)
    for t, e in m.equipment.items():
        b = e["bbox"]
        ax.add_patch(Rectangle((b[0] * sx - 4, b[1] * sy - 4), (b[2] - b[0]) * sx + 8, (b[3] - b[1]) * sy + 8,
                               fill=False, ec=BLUE, lw=1.6))
    for k, l in m.lines.items():
        pts = np.array(l["pts"])
        ax.plot(pts[:, 0] * sx, pts[:, 1] * sy, color=BLUE, lw=1.2, alpha=0.8)
    with pdfplumber.open(pdf) as p:
        ws = p.pages[0].extract_words()
    letters = {}
    for i, w in enumerate(ws):
        for j, u in enumerate(ws):
            if u["text"].isdigit() and len(u["text"]) == 3 and abs(u["x0"] - w["x0"]) < 12 and 0 < u["top"] - w["top"] < 14:
                letters[f"{w['text']}-{u['text']}"] = ((w["x0"] + w["x1"]) / 2, (w["top"] + u["bottom"]) / 2)
    for t, v in m.instruments.items():
        if t in letters:
            x, y = letters[t]
            ax.add_patch(plt.Circle((x * sx, y * sy), 17 * sx, fill=False, ec=METHOD_COLOR[v["method"]], lw=2.0))
    x0 = min(e["bbox"][0] for e in m.equipment.values()) * sx - 40
    x1 = max(e["bbox"][2] for e in m.equipment.values()) * sx + 90
    y0 = min(min(y for _, y in letters.values()) * sy - 40, min(e["bbox"][1] for e in m.equipment.values()) * sy - 40)
    y1 = max(max(y for _, y in letters.values()) * sy + 40, max(e["bbox"][3] for e in m.equipment.values()) * sy + 70)
    ax.set_xlim(x0, x1)
    ax.set_ylim(y1, y0)
    ax.axis("off")
    handles = [Line2D([], [], color=BLUE, lw=1.6, label="equipment / process line read"),
               Line2D([], [], marker="o", ls="", mfc="none", mec=BLUE, mew=2, ms=9, label="instrument tied by its signal line"),
               Line2D([], [], marker="o", ls="", mfc="none", mec=AQUA, mew=2, ms=9, label="tied via its loop (no signal line)"),
               Line2D([], [], marker="o", ls="", mfc="none", mec=ORANGE, mew=2, ms=9, label="tied by proximity, flagged for review"),
               Line2D([], [], marker="o", ls="", mfc="none", mec="#b8b7b3", mew=1, ms=9,
                      label="unmarked bubble: could not be read (overlap), flagged for review")]
    ax.legend(handles=handles, loc="lower left", bbox_to_anchor=(0, -0.16), ncol=3, frameon=False, fontsize=8)
    ax.set_title(f"What the reader extracted from synthetic drawing {drawing}", fontsize=12, loc="left")
    fig.tight_layout()
    DOCS.mkdir(exist_ok=True)
    fig.savefig(DOCS / out, bbox_inches="tight")
    plt.close(fig)
    return m
