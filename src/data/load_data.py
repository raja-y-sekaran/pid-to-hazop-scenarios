"""List the synthetic drawings and load their ground truth."""
import json

from src.utils.paths import DATA_RAW, GROUND_TRUTH

SETS = ("drawings", "drawings_hard")


def load_data(folder="drawings"):
    """Paths of the drawing PDFs in one set: 'drawings' (standard) or 'drawings_hard'."""
    return sorted((DATA_RAW / folder).glob("*.pdf"))


def load_truth(drawing: str) -> dict:
    """True content of a drawing, for scoring only (known because the drawings are synthetic)."""
    return json.loads((GROUND_TRUTH / f"{drawing}.json").read_text())
