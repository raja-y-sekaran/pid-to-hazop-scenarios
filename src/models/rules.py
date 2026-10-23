"""This project has no trained model: the reader is rule-based (line widths, arrowheads, ISA-5.1 tag grammar)
and the HAZOP engine is a guideword rule set. models/ holds the reader settings and a model card, so the
'model' is versioned like any other."""
import json

from src.utils.paths import MODELS

READER_SETTINGS = dict(process_line_width_min_pt=1.8, signal_line_width_max_pt=0.7, bubble_diameter_pt=[16, 30],
                       equipment_tag=r"^(T|V|C|P|E|K)-\d{3}[A-Z]?$", line_number=r'^\d{1,2}"-[A-Z]{1,2}-\d{4}$',
                       instrument_letters=r"^[AFLPTVWSEZ][DFQ]?[IRCTAESYVHLZ]{1,4}$",
                       attach_order=["signal line", "same loop", "proximity (flagged for review)"])


def save_model_card():
    (MODELS / "reader_settings.json").write_text(json.dumps(READER_SETTINGS, indent=2))
    (MODELS / "model_card.json").write_text(json.dumps(dict(
        model="Rule-based vector-PDF P&ID reader (pdfplumber) + guideword HAZOP draft engine; no trained weights",
        inputs="vector PDF P&IDs drawn to the conventions in src/data/generate_pids.py",
        not_supported="scanned / raster drawings, other symbol libraries, multi-sheet continuations",
        output="draft HAZOP worksheet for a HAZOP team to challenge; severity, likelihood and recommendations stay with the team",
        evaluation="scored against generator ground truth on 30 standard and 20 hard synthetic drawings (reports/metrics.json)",
    ), indent=2))
    return MODELS / "model_card.json"
