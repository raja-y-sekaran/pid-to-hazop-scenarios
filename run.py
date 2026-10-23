"""Read all synthetic P&IDs, score the reading, draft HAZOP worksheets, compare with drafts from the true content."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from pid_hazop import figures, pipeline  # noqa: E402

if __name__ == "__main__":
    res = pipeline.run()
    figures.annotated("SYN-PID-007")
    figures.annotated("SYN-HARD-003", folder="drawings_hard", out="annotated_pid_hard.png")
    print(json.dumps(res, indent=1))
