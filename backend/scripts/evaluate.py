"""Precision/recall/F1 + lead time from a labelled CSV.

CSV columns: clip,onset_s,impact_s
  clip      path to video (relative to the CSV)
  onset_s   second when rockfall begins; empty for a negative clip
  impact_s  second when rock reaches the danger zone (optional; defaults to onset_s)
Per clip, the first ALERT counts. Positive clip: alert at t >= onset - tol is TP, none is FN.
Negative clip with an alert, or positive clip alerting before onset - tol, is FP.
Lead time = impact_s - alert time (TP clips only).
"""
import argparse
import csv
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from rockfall.config import Settings  # noqa: E402
from rockfall.pipeline import run_offline  # noqa: E402


def evaluate(rows, cfg, tol=1.0, base="."):
    tp = fp = fn = tn = 0
    leads = []
    for r in rows:
        onset = float(r["onset_s"]) if r.get("onset_s") else None
        impact = float(r["impact_s"]) if r.get("impact_s") else onset
        alerts = [e["ts"] for e in run_offline(os.path.join(base, r["clip"]), cfg) if e["type"] == "ALERT"]
        first = alerts[0] if alerts else None
        if onset is None:
            fp, tn = (fp + 1, tn) if first is not None else (fp, tn + 1)
        elif first is None:
            fn += 1
        elif first < onset - tol:
            fp += 1
            fn += 1
        else:
            tp += 1
            leads.append(impact - first)
    p = tp / (tp + fp) if tp + fp else 0.0
    rc = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * p * rc / (p + rc) if p + rc else 0.0
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn, "precision": p, "recall": rc, "f1": f1,
            "mean_lead_time_s": sum(leads) / len(leads) if leads else None}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--tol", type=float, default=1.0)
    a = ap.parse_args()
    with open(a.csv) as f:
        rows = list(csv.DictReader(f))
    for k, v in evaluate(rows, Settings.from_env(), a.tol, os.path.dirname(os.path.abspath(a.csv))).items():
        print(f"{k}: {v if not isinstance(v, float) else round(v, 3)}")
