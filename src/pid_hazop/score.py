"""Score what the reader found against the generator's ground truth."""
from __future__ import annotations

import json
from pathlib import Path


def _prf(found: set, true: set) -> dict:
    tp = len(found & true)
    return dict(true=len(true), found=len(found), correct=tp,
                precision=round(tp / len(found), 4) if found else None,
                recall=round(tp / len(true), 4) if true else None)


def score(model, truth: dict) -> dict:
    s = {}
    s["equipment"] = _prf(set(model.equipment), {e["tag"] for e in truth["equipment"]})
    s["lines (number, from, to)"] = _prf({(k, v["from"], v["to"]) for k, v in model.lines.items()},
                                         {(l["line_no"], l["from"], l["to"]) for l in truth["lines"]})
    s["valves on lines"] = _prf({(k, v) for k, l in model.lines.items() for v in l["valves"]},
                                {(l["line_no"], v) for l in truth["lines"] for v in l["valves"]})
    s["relief valves"] = _prf(set(model.relief_valves.items()), {(r["tag"], r["equipment"]) for r in truth["relief_valves"]})
    s["instruments (tag, attached to)"] = _prf({(k, v["attached_to"]) for k, v in model.instruments.items()},
                                               {(i["tag"], i["attached_to"]) for i in truth["instruments"]})
    no_sig = {i["tag"] for i in truth["instruments"] if not i["signal_line_drawn"]}
    s["instruments without signal line"] = _prf(
        {(k, v["attached_to"]) for k, v in model.instruments.items() if k in no_sig},
        {(i["tag"], i["attached_to"]) for i in truth["instruments"] if i["tag"] in no_sig})
    return s


def load_truth(drawing: str, root: Path) -> dict:
    return json.loads((root / "data" / "ground_truth" / f"{drawing}.json").read_text())
