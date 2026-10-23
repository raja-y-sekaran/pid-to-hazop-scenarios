import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pid_hazop.hazop import Graph, draft_hazop  # noqa: E402
from pid_hazop.reader import EQUIP_RE, LETTERS_RE, LINE_RE, _dist_to_polyline, read_pid  # noqa: E402
from pid_hazop.score import load_truth, score  # noqa: E402


@pytest.mark.parametrize("tag,ok", [("V-301", True), ("P-302A", True), ("X-301", False), ("V-30", False)])
def test_equipment_tag_grammar(tag, ok):
    assert bool(EQUIP_RE.match(tag)) is ok


@pytest.mark.parametrize("text,ok", [("LIC", True), ("LSHH", True), ("PAH", True), ("FT", True),
                                     ("NOT", False), ("REAL", False), ("DWG", False)])
def test_isa_function_letters(text, ok):
    assert bool(LETTERS_RE.match(text)) is ok


def test_line_number_grammar():
    assert LINE_RE.match('4"-P-3005') and not LINE_RE.match("P-3005")


def test_point_to_polyline_distance():
    import numpy as np
    assert _dist_to_polyline(np.array([5.0, 3.0]), [(0, 0), (10, 0)]) == pytest.approx(3.0)
    assert _dist_to_polyline(np.array([12.0, 0.0]), [(0, 0), (10, 0)]) == pytest.approx(2.0)


def test_reader_matches_ground_truth_on_a_sample_drawing():
    m = read_pid(ROOT / "data" / "drawings" / "SYN-PID-002.pdf")
    s = score(m, load_truth("SYN-PID-002", ROOT))
    for k, v in s.items():
        if v["true"]:
            assert v["precision"] == 1.0 and v["recall"] == 1.0, k


TINY = Graph(
    equipment={"V-101": "V", "P-102A": "P", "T-103": "T"},
    lines={'4"-P-1001': {"from": "V-101", "to": "P-102A", "valves": ["LV-110"]},
           '3"-P-1002': {"from": "P-102A", "to": "T-103", "valves": []}},
    instruments={"LT-110": "V-101", "LIC-110": "V-101", "LAH-110": "V-101", "LAL-110": "V-101", "LSHH-111": "V-101",
                 "LT-120": "T-103", "LIC-120": "T-103"},
    relief={"PSV-112": "V-101"},
)


def _row(rows, eq, dev):
    return next(r for r in rows if r.equipment == eq and r.deviation == dev)


def test_hazop_draft_hand_checked_rows():
    rows = draft_hazop(TINY)
    assert [r.node.split()[1] for r in rows][::3][:2] == ["V-101", "P-102A"]  # flow order
    hl = _row(rows, "V-101", "High level")
    assert "LV-110 fails closed / LIC mis-set" in hl.causes and "downstream P-102A stopped" in hl.causes
    assert hl.safeguards == ["LAH-110 (high-level alarm, operator response)", "LSHH-111 (independent high-high level trip)"]
    assert hl.gap == ""
    ll = _row(rows, "V-101", "Low level")
    assert "loss of suction to P-102A: cavitation, seal damage" in ll.consequences and ll.gap == ""
    rev = _row(rows, "P-102A", "Reverse flow")
    assert rev.safeguards == [] and "No check valve" in rev.gap
    hp = _row(rows, "T-103", "High pressure")
    assert "P-102A deadhead / shut-off pressure" in hp.causes and "No relief valve" in hp.gap
    assert "No independent high-high level trip" in _row(rows, "T-103", "High level").gap


def test_missing_safeguard_creates_a_gap_not_a_silent_pass():
    g = Graph(dict(TINY.eq), dict(TINY.lines), {k: v for k, v in TINY.inst.items() if k != "LSHH-111"}, dict(TINY.relief))
    assert "No independent high-high level trip" in _row(draft_hazop(g), "V-101", "High level").gap
