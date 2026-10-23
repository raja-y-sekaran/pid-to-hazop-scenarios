"""Draft HAZOP worksheet from a plant model read off the P&ID.

One node per equipment item (with its inlet line). For each node, the guideword/parameter
deviations that apply to that equipment type are listed with:
  * causes that come from the drawing's topology (upstream pump, outlet control valve, ...)
  * consequences in plant terms
  * safeguards actually found on the drawing, each with its tag
  * a gap note where an expected safeguard is not on the drawing

This is a starting draft for a HAZOP team to challenge, not a HAZOP. Severity, likelihood and
the final recommendations stay with the team.
"""
from __future__ import annotations

from dataclasses import dataclass, field

TYPE_NAME = {"T": "tank", "V": "drum", "C": "column", "P": "pump", "E": "heat exchanger", "K": "compressor"}
CONTAINERS = ("T", "V", "C")


@dataclass
class Row:
    node: str
    equipment: str
    parameter: str
    guideword: str
    deviation: str
    causes: list
    consequences: list
    safeguards: list = field(default_factory=list)
    gap: str = ""

    def as_dict(self):
        return dict(node=self.node, equipment=self.equipment, parameter=self.parameter, guideword=self.guideword,
                    deviation=self.deviation, causes="; ".join(self.causes), consequences="; ".join(self.consequences),
                    safeguards_on_drawing="; ".join(self.safeguards) or "none found on drawing",
                    gap_for_team_review=self.gap)


class Graph:
    """Convenience view of the plant model (works for the reader's output and for ground truth)."""

    def __init__(self, equipment: dict, lines: dict, instruments: dict, relief: dict):
        self.eq = equipment          # tag -> type letter
        self.lines = lines           # line_no -> {from, to, valves}
        self.inst = instruments      # tag -> attached_to
        self.relief = relief         # psv tag -> equipment

    @classmethod
    def from_model(cls, m):
        return cls({t: t[0] for t in m.equipment}, {k: {"from": v["from"], "to": v["to"], "valves": v["valves"]}
                                                    for k, v in m.lines.items()},
                   {k: v["attached_to"] for k, v in m.instruments.items()}, dict(m.relief_valves))

    @classmethod
    def from_truth(cls, t):
        return cls({e["tag"]: e["tag"][0] for e in t["equipment"]},
                   {l["line_no"]: {"from": l["from"], "to": l["to"], "valves": l["valves"]} for l in t["lines"]},
                   {i["tag"]: i["attached_to"] for i in t["instruments"]},
                   {r["tag"]: r["equipment"] for r in t["relief_valves"]})

    def inlets(self, e):
        return [(k, l) for k, l in self.lines.items() if l["to"] == e]

    def outlets(self, e):
        return [(k, l) for k, l in self.lines.items() if l["from"] == e]

    def on(self, item, *funcs):
        """Instrument tags on an equipment item or line whose function letters are in funcs."""
        return sorted(t for t, a in self.inst.items() if a == item and t.split("-")[0] in funcs)

    def valves(self, line_no, prefix):
        return [v for v in self.lines[line_no]["valves"] if v.startswith(prefix)]

    def flow_order(self):
        """Equipment in process-flow order: start from items with no inlet, follow the lines."""
        order, seen = [], set()
        starts = sorted(e for e in self.eq if not self.inlets(e)) or sorted(self.eq)
        stack = list(reversed(starts))
        while stack:
            e = stack.pop()
            if e in seen:
                continue
            seen.add(e)
            order.append(e)
            stack += sorted((l["to"] for _, l in self.outlets(e) if l["to"] and l["to"] not in seen), reverse=True)
        return order + sorted(set(self.eq) - seen)

    def psv(self, e):
        return sorted(t for t, a in self.relief.items() if a == e)


def _fmt(tags, what):
    return [f"{t} ({what})" for t in tags]


def draft_hazop(g: Graph) -> list[Row]:
    rows = []
    for n, e in enumerate(g.flow_order(), start=1):
        kind = g.eq[e]
        ins, outs = g.inlets(e), g.outlets(e)
        src = [l["from"] for _, l in ins]
        dst = [l["to"] for _, l in outs]
        node = f"N{n:02d} {e} ({TYPE_NAME[kind]})" + (f" incl. inlet {ins[0][0]}" if ins else "")
        R = lambda *a, **k: rows.append(Row(node, e, *a, **k))

        if kind in CONTAINERS:
            out_lv = [v for k, _ in outs for v in g.valves(k, "LV")]
            dst_pumps = [d for d in dst if d and d[0] == "P"]
            dst_comp = [d for d in dst if d and d[0] == "K"]
            # High level
            causes = [f"{v} fails closed / LIC mis-set" for v in out_lv]
            causes += [f"downstream {d} stopped" for d in dst if d] + [f"inflow from {s} above outlet capacity" for s in src if s]
            cons = {"T": "tank overfill, loss of containment", "V": f"liquid carry-over to {', '.join(dst) or 'downstream'}",
                    "C": "column flooding, off-spec product"}[kind]
            if dst_comp:
                cons += f"; liquid into compressor {dst_comp[0]} (machine damage)"
            sg = _fmt(g.on(e, "LAH"), "high-level alarm, operator response") + _fmt(g.on(e, "LSHH"), "independent high-high level trip")
            gap = "" if g.on(e, "LSHH") else "No independent high-high level trip found on drawing; team to decide if one is needed (LOPA)."
            R("Level", "More", "High level", causes or ["inflow above outlet capacity"], [cons], sg, gap)
            # Low level
            causes = [f"{v} fails open" for v in out_lv] + [f"loss of feed from {s}" for s in src if s] or ["outlet flow above inflow"]
            cons = [f"loss of suction to {p}: cavitation, seal damage" for p in dst_pumps]
            if out_lv:
                cons.append(f"gas blow-by through {out_lv[0]} to {dst[0] if dst else 'downstream'}")
            sg = _fmt(g.on(e, "LAL"), "low-level alarm, operator response")
            gap = "" if (sg or not dst_pumps) else "No low-level alarm or trip protecting the downstream pump found on drawing."
            R("Level", "Less", "Low level", causes, cons or ["level lost, downstream starved"], sg, gap)
            # High pressure
            causes = [f"outlet blocked ({v} closed)" for v in out_lv] + ["external fire"]
            causes += [f"{s} deadhead / shut-off pressure" for s in src if s and s[0] in "PK"]
            sg = _fmt(g.on(e, "PAH"), "high-pressure alarm") + _fmt(g.psv(e), "relief valve")
            gap = "" if g.psv(e) else "No relief valve found on drawing; confirm overpressure protection (may be on another sheet)."
            R("Pressure", "More", "High pressure", causes, ["overpressure, possible loss of containment"], sg, gap)
            # High temperature (only when heated/cooled upstream or measured)
            hx = [s for s in src if s and s[0] == "E"]
            if hx or g.on(e, "TT"):
                causes = [f"loss of cooling in {h}" for h in hx] or ["high feed temperature"]
                sg = _fmt(g.on(e, "TAH"), "high-temperature alarm") + [f"{t} (indication only)" for t in g.on(e, "TT")]
                for h in hx:
                    for k, l in g.inlets(e):
                        sg += _fmt(g.on(k, "TAH"), "high-temperature alarm on inlet")
                R("Temperature", "More", "High temperature", causes, ["vapour generation, pressure rise"], sg,
                  "" if any("alarm" in s for s in sg) else "No high-temperature alarm found; temperature indication only or none.")

        elif kind == "P":
            dl = [k for k, _ in outs]
            nrv = [v for k in dl for v in g.valves(k, "NRV")]
            sg = []
            for s in src:
                if s and s[0] in CONTAINERS:
                    sg += _fmt(g.on(s, "LAL"), f"low level on suction vessel {s}")
            for k in dl:
                sg += _fmt(g.on(k, "FAL"), "low-flow alarm")
            R("Flow", "No", "No / low flow", [f"low level in {s}" for s in src if s] + ["pump trip (power, mechanical)"]
              + [f"{v} closed" for k in dl for v in g.valves(k, "FV")],
              ["pump runs dry or deadheaded: overheating, seal failure", f"loss of feed to {', '.join(dst) or 'downstream'}"],
              sg, "" if sg else "No low-flow or low-suction-level protection found; consider minimum-flow protection.")
            R("Flow", "Reverse", "Reverse flow", ["pump stops while discharge side is at higher pressure"],
              [f"backflow into {', '.join(s for s in src if s) or 'suction'}; reverse rotation"],
              _fmt(nrv, "check valve"), "" if nrv else f"No check valve found on discharge line {', '.join(dl)}.")
            down_psv = [p for d in dst if d for p in g.psv(d)]
            R("Pressure", "More", "High discharge pressure", [f"discharge blocked ({v} closed)" for k in dl for v in g.valves(k, "FV")]
              or ["discharge blocked downstream"], ["pump deadheaded; downstream overpressure if shut-off exceeds design"],
              _fmt(down_psv, "relief on downstream equipment"), "" if down_psv else "Confirm pump shut-off pressure against downstream design pressure.")

        elif kind == "E":
            ol = [k for k, _ in outs]
            sg = [s for k in ol for s in _fmt(g.on(k, "TAH"), "high-temperature alarm on outlet")]
            ind = [f"{t} (indication only)" for k in ol for t in g.on(k, "TT")]
            R("Temperature", "More", "High outlet temperature", ["loss of cooling / heating medium upset", "tube fouling"],
              [f"high temperature to {', '.join(dst) or 'downstream'}"], sg + ind,
              "" if sg else "No high-temperature alarm on the outlet found on drawing.")
            R("Flow", "Less", "Low / no process flow", [f"upstream {s} stops" for s in src if s] or ["upstream stops"],
              ["overheating of process side, thermal stress"], [], "Team to confirm protection (not identifiable from this drawing).")
            R("Composition", "Other than", "Tube leak", ["tube failure / corrosion"], ["cross-contamination between process and utility"],
              [], "Not detectable from this drawing; confirm leak detection philosophy.")

        elif kind == "K":
            up = [s for s in src if s and s[0] in CONTAINERS]
            sg = [x for s in up for x in _fmt(g.on(s, "LSHH"), f"high-high level trip on suction drum {s}") + _fmt(g.on(s, "LAH"), f"high-level alarm on {s}")]
            R("Composition", "As well as", "Liquid in suction", [f"high level in suction drum {s}" for s in up] or ["liquid carry-over"],
              ["liquid slug damage to compressor"], sg, "" if any("trip" in x for x in sg) else "No high-high level trip on the suction drum found; consider one.")
            vib = _fmt(g.on(e, "VAH"), "high-vibration alarm") + [f"{t} (indication only)" for t in g.on(e, "VT")]
            R("Vibration", "More", "High vibration", ["bearing wear", "surge", "misalignment"], ["machine damage, seal failure, release"],
              vib, "" if g.on(e, "VAH") else "No vibration alarm found on drawing.")
            R("Flow", "Less", "Low flow / surge", [f"downstream blocked" for _ in outs] or ["low suction flow"], ["surge, machine damage"],
              [], "Anti-surge protection not identifiable from this drawing; team to confirm.")
    return rows
