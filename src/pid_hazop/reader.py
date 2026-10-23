"""Read a vector P&ID (PDF) into a plant model: equipment, process lines with flow direction,
valves, relief valves and instruments, each with how it was found.

Only text and geometry from the PDF are used: tag grammar (ISA-5.1 style) identifies items,
line widths separate process lines from signal lines, arrowheads give flow direction, and
distances tie labels and instruments to the items they belong to.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import numpy as np
import pdfplumber

EQUIP_RE = re.compile(r"^(T|V|C|P|E|K)-\d{3}[A-Z]?$")
VALVE_RE = re.compile(r"^(LV|FV|PV|TV|NRV)-\d{3}$")
PSV_RE = re.compile(r"^PSV-\d{3}$")
LINE_RE = re.compile(r'^\d{1,2}"-[A-Z]{1,2}-\d{4}$')
# ISA-5.1 style function letters: measured variable (+ optional modifier) then readout/output letters
LETTERS_RE = re.compile(r"^[AFLPTVWSEZ][DFQ]?[IRCTAESYVHLZ]{1,4}$")
LOOP_RE = re.compile(r"^\d{3}$")
EQUIP_TYPES = {"T": "tank", "V": "drum", "C": "column", "P": "pump", "E": "heat exchanger", "K": "compressor"}


@dataclass
class PlantModel:
    drawing: str
    equipment: dict = field(default_factory=dict)      # tag -> {type, bbox}
    lines: dict = field(default_factory=dict)          # line_no -> {from, to, valves, pts}
    instruments: dict = field(default_factory=dict)    # tag -> {attached_to, method}
    relief_valves: dict = field(default_factory=dict)  # tag -> equipment
    unresolved: list = field(default_factory=list)


def _center(o):
    return np.array([(o["x0"] + o["x1"]) / 2, (o["top"] + o["bottom"]) / 2])


def _bbox(o):
    return np.array([o["x0"], o["top"], o["x1"], o["bottom"]], float)


def _in_bbox(p, b, pad=0.0):
    return b[0] - pad <= p[0] <= b[2] + pad and b[1] - pad <= p[1] <= b[3] + pad


def _dist_to_bbox(p, b):
    dx = max(b[0] - p[0], 0, p[0] - b[2])
    dy = max(b[1] - p[1], 0, p[1] - b[3])
    return float(np.hypot(dx, dy))


def _dist_to_polyline(p, pts):
    best = np.inf
    for a, b in zip(pts[:-1], pts[1:]):
        a, b = np.asarray(a, float), np.asarray(b, float)
        ab = b - a
        t = 0.0 if not ab.any() else np.clip(np.dot(p - a, ab) / np.dot(ab, ab), 0, 1)
        best = min(best, float(np.linalg.norm(p - (a + t * ab))))
    return best


def _paths(page):
    """All stroked/filled vector objects as dicts with pts (top-based coordinates)."""
    out = []
    for o in page.curves + page.lines:
        out.append(dict(pts=[tuple(map(float, p)) for p in o["pts"]], lw=round(o.get("linewidth") or 0, 2),
                        fill=bool(o.get("fill")), bbox=_bbox(o)))
    for o in page.rects:
        out.append(dict(pts=None, lw=round(o.get("linewidth") or 0, 2), fill=bool(o.get("fill")), bbox=_bbox(o)))
    return out


def read_pid(pdf_path, process_lw=1.8, signal_lw=0.7, bubble_d=(16, 30)) -> PlantModel:
    with pdfplumber.open(pdf_path) as pdf:
        page = pdf.pages[0]
        words = page.extract_words(keep_blank_chars=False)
        paths = _paths(page)
    m = PlantModel(drawing=str(pdf_path).split("/")[-1].replace(".pdf", ""))
    W = [dict(text=w["text"], c=_center(w)) for w in words]
    # Title block: the large plain rectangle holding the drawing number. Its text is not process content.
    blocks = [p["bbox"] for p in paths if p["pts"] is None and any(
        _in_bbox(w["c"], p["bbox"]) and w["text"] == "DWG" for w in W)]
    if blocks:  # the smallest such rectangle (the page background also contains the text)
        tb = min(blocks, key=lambda b: (b[2] - b[0]) * (b[3] - b[1]))
        W = [w for w in W if not _in_bbox(w["c"], tb)]

    # 1. Equipment: tag text inside a closed outline that is bigger than an instrument bubble.
    outlines = [p for p in paths if not p["fill"] and 1.2 <= p["lw"] <= 1.6
                and (p["bbox"][2] - p["bbox"][0]) > bubble_d[0]]
    for w in W:
        if EQUIP_RE.match(w["text"]):
            inside = [p for p in outlines if _in_bbox(w["c"], p["bbox"])]
            if inside:
                b = min(inside, key=lambda p: (p["bbox"][2] - p["bbox"][0]) * (p["bbox"][3] - p["bbox"][1]))["bbox"]
                m.equipment[w["text"]] = dict(type=EQUIP_TYPES[w["text"][0]], bbox=b)
            else:
                m.unresolved.append(f"equipment tag {w['text']} has no outline")

    # 2. Process lines: thick polylines. Flow direction from the filled arrowhead at one end.
    plines = [p for p in paths if p["pts"] and p["lw"] >= process_lw and not p["fill"] and len(p["pts"]) >= 2]
    arrows = [np.mean(p["pts"], axis=0) for p in paths if p["fill"] and p["pts"] and
              (p["bbox"][2] - p["bbox"][0]) < 20 and (p["bbox"][3] - p["bbox"][1]) < 20]

    def nearest_equipment(pt, tol=12.0):
        if not m.equipment:
            return None
        tag, d = min(((t, _dist_to_bbox(pt, e["bbox"])) for t, e in m.equipment.items()), key=lambda x: x[1])
        return tag if d <= tol else None

    raw_lines = []
    for p in plines:
        a, b = np.array(p["pts"][0]), np.array(p["pts"][-1])
        da = min((np.linalg.norm(a - x) for x in arrows), default=np.inf)
        db = min((np.linalg.norm(b - x) for x in arrows), default=np.inf)
        has_arrow = min(da, db) < 15
        if has_arrow and da < db:
            a, b = b, a  # arrowhead marks the downstream end
        elif not has_arrow and a[0] > b[0]:
            a, b = b, a  # no arrowhead: fall back on the left-to-right drawing convention
        raw_lines.append(dict(frm=nearest_equipment(a), to=nearest_equipment(b), pts=p["pts"], arrow=has_arrow))

    # 3. Line numbers: the line-number text sits next to its line.
    for w in W:
        if LINE_RE.match(w["text"]):
            i = int(np.argmin([_dist_to_polyline(w["c"], l["pts"]) for l in raw_lines])) if raw_lines else None
            if i is not None and _dist_to_polyline(w["c"], raw_lines[i]["pts"]) < 25:
                raw_lines[i]["line_no"] = w["text"]
    for l in raw_lines:
        no = l.get("line_no") or f"UNNUMBERED-{len(m.lines) + 1}"
        if not l["arrow"]:
            m.unresolved.append(f"line {no}: no arrowhead, flow direction assumed left to right")
        m.lines[no] = {"from": l["frm"], "to": l["to"], "valves": [], "pts": l["pts"]}

    # 4. Valves on lines, relief valves on equipment.
    for w in W:
        if VALVE_RE.match(w["text"]) and m.lines:
            no = min(m.lines, key=lambda k: _dist_to_polyline(w["c"], m.lines[k]["pts"]))
            if _dist_to_polyline(w["c"], m.lines[no]["pts"]) < 45:
                m.lines[no]["valves"].append(w["text"])
            else:
                m.unresolved.append(f"valve {w['text']} not near any process line")
        elif PSV_RE.match(w["text"]):
            eq = nearest_equipment(w["c"], tol=80)
            m.relief_valves[w["text"]] = eq
            if eq is None:
                m.unresolved.append(f"relief valve {w['text']} not near any equipment")

    # 5. Instrument bubbles: small circles holding function letters above a loop number.
    circles = [p for p in paths if p["pts"] and not p["fill"] and 0.75 <= p["lw"] <= 0.95
               and bubble_d[0] <= p["bbox"][2] - p["bbox"][0] <= bubble_d[1]
               and abs((p["bbox"][2] - p["bbox"][0]) - (p["bbox"][3] - p["bbox"][1])) < 3]
    bubbles, used = [], set()
    for c in circles:
        cb = c["bbox"]
        cc = np.array([(cb[0] + cb[2]) / 2, (cb[1] + cb[3]) / 2])
        inside = [w for w in W if _in_bbox(w["c"], cb)]
        letters = [w["text"] for w in inside if LETTERS_RE.match(w["text"]) and w["c"][1] < cc[1]]
        loop = [w["text"] for w in inside if LOOP_RE.match(w["text"]) and w["c"][1] > cc[1]]
        if len(letters) == 1 and len(loop) == 1:
            bubbles.append(dict(tag=f"{letters[0]}-{loop[0]}", c=cc, r=(cb[2] - cb[0]) / 2))
            used.update(id(w) for w in inside)
        elif letters or loop:
            m.unresolved.append(f"overlapping bubbles near ({cc[0]:.0f}, {cc[1]:.0f}): "
                                f"text {' '.join(letters + loop)} could not be paired - check by eye")
            used.update(id(w) for w in inside)
    for w in W:  # instrument-style text that did not end up in any bubble
        if id(w) not in used and (LOOP_RE.match(w["text"]) or
                                  LETTERS_RE.match(w["text"])):
            if not any(_in_bbox(w["c"], c["bbox"], pad=2) for c in circles):
                m.unresolved.append(f"instrument-like text '{w['text']}' at ({w['c'][0]:.0f}, {w['c'][1]:.0f}) "
                                    f"is not inside a readable bubble")

    # 6. Attach each bubble: (a) its signal line, (b) another bubble of the same loop, (c) proximity.
    signals = [p for p in paths if p["pts"] and p["lw"] <= signal_lw and not p["fill"]]
    for bub in bubbles:
        for s in signals:
            ends = [np.array(s["pts"][0]), np.array(s["pts"][-1])]
            for i in (0, 1):
                if abs(np.linalg.norm(ends[i] - bub["c"]) - bub["r"]) < 3:
                    far = ends[1 - i]
                    eq = next((t for t, e in m.equipment.items() if _in_bbox(far, e["bbox"], pad=3)), None)
                    ln = None
                    if eq is None and m.lines:
                        ln = min(m.lines, key=lambda k: _dist_to_polyline(far, m.lines[k]["pts"]))
                        ln = ln if _dist_to_polyline(far, m.lines[ln]["pts"]) < 3 else None
                    if eq or ln:
                        m.instruments[bub["tag"]] = dict(attached_to=eq or ln, method="signal line")
    for bub in bubbles:
        if bub["tag"] in m.instruments:
            continue
        loop = bub["tag"].split("-")[1]
        sib = [v["attached_to"] for k, v in m.instruments.items() if k.endswith("-" + loop) and v["method"] == "signal line"]
        if sib:
            m.instruments[bub["tag"]] = dict(attached_to=sib[0], method="same loop")
            continue
        cand = [(t, _dist_to_bbox(bub["c"], e["bbox"])) for t, e in m.equipment.items()]
        cand += [(k, _dist_to_polyline(bub["c"], l["pts"])) for k, l in m.lines.items()]
        tag, d = min(cand, key=lambda x: x[1])
        m.instruments[bub["tag"]] = dict(attached_to=tag, method="proximity")
        m.unresolved.append(f"instrument {bub['tag']}: no signal line, attached to nearest item {tag} ({d:.0f} pt)")
    return m
