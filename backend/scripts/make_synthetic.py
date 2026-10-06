"""Generate a synthetic rockfall video: python scripts/make_synthetic.py out.mp4"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from rockfall.synthetic import make_synthetic  # noqa: E402

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("out", nargs="?", default="data/synthetic.mp4")
    ap.add_argument("--frames", type=int, default=150)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--rocks", type=int, default=3)
    ap.add_argument("--fall-start", type=int, default=40, help="frame where first rock detaches")
    a = ap.parse_args()
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    print(json.dumps(make_synthetic(a.out, a.frames, seed=a.seed, rocks=a.rocks, fall_start=a.fall_start)))
