"""Run the project end to end (course layout: data -> features (read the P&ID) -> HAZOP draft -> evaluation).

    python main.py                       # read all 50 synthetic drawings, draft HAZOPs, score, figures
    python main.py --regenerate          # redraw the synthetic drawings first (--seed to change them)
"""
import argparse
import json
import sys

from src import pipeline
from src.data import generate_pids
from src.models import rules
from src.utils import plots


def run_all(quiet=False):
    res = pipeline.run()
    plots.annotated("SYN-PID-007")
    plots.annotated("SYN-HARD-003", folder="drawings_hard", out="annotated_pid_hard.png")
    rules.save_model_card()
    if not quiet:
        print(json.dumps(res, indent=1))
    return res


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--regenerate", action="store_true")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()
    if a.regenerate:
        sys.argv = ["generate_pids", "--seed", str(a.seed)]
        generate_pids.main()
    run_all(a.quiet)
