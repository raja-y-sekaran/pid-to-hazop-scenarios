"""Read every drawing, score the reading, draft the HAZOP worksheet, and compare the draft built from
the reader's output with the draft built from the true drawing content."""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import pandas as pd

from .hazop import Graph, draft_hazop
from .reader import read_pid
from .score import load_truth, score

ROOT = Path(__file__).resolve().parents[2]
DATA, OUT, DOCS = ROOT / "data", ROOT / "outputs", ROOT / "docs"


def row_key(r):
    return (r.equipment, r.deviation)


def compare_hazop(rows_read, rows_true) -> dict:
    """Row-level agreement: same deviations on the same equipment, same safeguards, same gap call."""
    a, b = {row_key(r): r for r in rows_read}, {row_key(r): r for r in rows_true}
    common = a.keys() & b.keys()
    same_sg = sum(sorted(a[k].safeguards) == sorted(b[k].safeguards) for k in common)
    same_gap = sum(bool(a[k].gap) == bool(b[k].gap) for k in common)
    return dict(rows_true=len(b), rows_read=len(a), rows_in_both=len(common), same_safeguards=same_sg, same_gap_call=same_gap,
                rows_identical=sum(sorted(a[k].safeguards) == sorted(b[k].safeguards) and a[k].gap == b[k].gap
                                   and a[k].causes == b[k].causes for k in common))


def workbook(model, rows, path):
    reg = pd.concat([
        pd.DataFrame([dict(item=t, kind="equipment", detail=e["type"], found_by="tag inside outline")
                      for t, e in model.equipment.items()]),
        pd.DataFrame([dict(item=k, kind="process line", detail=f"{l['from']} -> {l['to']}; valves: {', '.join(l['valves']) or '-'}",
                           found_by="thick polyline + arrowhead") for k, l in model.lines.items()]),
        pd.DataFrame([dict(item=t, kind="relief valve", detail=f"on {e}", found_by="nearest equipment")
                      for t, e in model.relief_valves.items()]),
        pd.DataFrame([dict(item=t, kind="instrument", detail=f"on {v['attached_to']}", found_by=v["method"])
                      for t, v in model.instruments.items()]),
    ], ignore_index=True)
    with pd.ExcelWriter(path) as xw:
        pd.DataFrame({"Read me": [
            f"Drawing {model.drawing} (synthetic). Draft generated from the P&ID only.",
            "HAZOP_draft: starting point for a HAZOP team. Causes, consequences and safeguards must be challenged;",
            "severity, likelihood and recommendations are the team's decision.",
            "Safeguards listed are only those found on this drawing, each with its tag.",
            "Review_flags: anything the reader was unsure about. Check these on the drawing first.",
        ]}).to_excel(xw, sheet_name="README", index=False)
        pd.DataFrame([r.as_dict() for r in rows]).to_excel(xw, sheet_name="HAZOP_draft", index=False)
        reg.to_excel(xw, sheet_name="Drawing_register", index=False)
        pd.DataFrame({"flag": model.unresolved or ["none"]}).to_excel(xw, sheet_name="Review_flags", index=False)


def run():
    (OUT / "hazop").mkdir(parents=True, exist_ok=True)
    results = {}
    per_drawing = []
    for folder in ("drawings", "drawings_hard"):
        tot, hz = defaultdict(lambda: [0, 0, 0]), defaultdict(int)
        for pdf in sorted((DATA / folder).glob("*.pdf")):
            m = read_pid(pdf)
            truth = load_truth(m.drawing, ROOT)
            s = score(m, truth)
            for k, v in s.items():
                t = tot[k]
                t[0] += v["true"]; t[1] += v["found"]; t[2] += v["correct"]
            rows_read = draft_hazop(Graph.from_model(m))
            rows_true = draft_hazop(Graph.from_truth(truth))
            c = compare_hazop(rows_read, rows_true)
            for k, v in c.items():
                hz[k] += v
            hz["gaps_true"] += sum(bool(r.gap) for r in rows_true)
            workbook(m, rows_read, OUT / "hazop" / f"{m.drawing}_HAZOP_draft.xlsx")
            per_drawing.append(dict(set=folder, drawing=m.drawing, review_flags=len(m.unresolved),
                                    instruments_true=s["instruments (tag, attached to)"]["true"],
                                    instruments_correct=s["instruments (tag, attached to)"]["correct"], **c))
        results[folder] = dict(
            reading={k: dict(true=t, found=f, correct=c, precision=round(c / f, 4) if f else None,
                             recall=round(c / t, 4) if t else None) for k, (t, f, c) in tot.items()},
            hazop=dict(hz))
    pd.DataFrame(per_drawing).to_csv(OUT / "per_drawing_results.csv", index=False)
    (OUT / "metrics.json").write_text(json.dumps(results, indent=2))
    return results
