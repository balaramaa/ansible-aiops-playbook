#!/usr/bin/env python3
"""
mttr_analyzer.py — Chapter 7, Listing 7-9
Compute MTTR from timestamps in the self-healing audit log.

MTTR per incident = (resolution timestamp) - (start timestamp).
  start      : the `detected=` field if the playbook was passed the alert's
               startsAt time, otherwise the first record for the incident
               (playbook start; this then measures remediation time only).
  resolution : the first SUCCESS record. Incidents ending in FAILED or
               ESCALATE are counted as escalated and excluded from MTTR.
Nothing is assumed: with no complete incident pairs the report says
"insufficient data" instead of inventing a number.

Author : Balaramakrishna Alti
GitHub : https://github.com/balaramaa/ansible-aiops-playbook

Usage:
    python3 mttr_analyzer.py [--log PATH] [--json]
"""
import argparse, json, re, statistics
from collections import defaultdict
from datetime import datetime
from pathlib import Path

AUDIT_LOG = Path("/var/log/self_healing_audit.log")
LINE = re.compile(r"^(?P<ts>\S+)\s+incident=(?P<inc>\S+)\s+type=(?P<type>\S+)(?P<rest>.*)$")


def parse_ts(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def parse_audit_log(path):
    recs = []
    if not path.exists():
        return recs
    for line in path.read_text().splitlines():
        m = LINE.match(line.strip())
        if not m:
            continue
        try:
            ts = parse_ts(m["ts"])
        except ValueError:
            continue
        rest = m["rest"]
        det = re.search(r"detected=(\S+)", rest)
        try:
            detected = parse_ts(det[1]) if det else None
        except ValueError:
            detected = None
        up = rest.upper()
        outcome = ("SUCCESS" if "SUCCESS" in up else
                   "FAILED" if "FAILED" in up else
                   "ESCALATE" if "ESCALAT" in up else "INFO")
        recs.append({"ts": ts, "incident": m["inc"], "type": m["type"],
                     "detected": detected, "outcome": outcome})
    return recs


def compute_mttr(recs):
    by_inc = defaultdict(list)
    for r in recs:
        by_inc[r["incident"]].append(r)
    groups = defaultdict(lambda: {"durations": [], "auto": 0, "escalated": 0, "open": 0})
    for events in by_inc.values():
        events.sort(key=lambda r: r["ts"])
        g = groups[events[0]["type"]]
        start = next((e["detected"] for e in events if e["detected"]), events[0]["ts"])
        done = next((e for e in events if e["outcome"] == "SUCCESS"), None)
        if done is not None:
            g["auto"] += 1
            g["durations"].append((done["ts"] - start).total_seconds())
        elif any(e["outcome"] in ("FAILED", "ESCALATE") for e in events):
            g["escalated"] += 1
        else:
            g["open"] += 1
    out = {}
    for t, g in groups.items():
        d = g["durations"]
        out[t] = {"incidents": g["auto"] + g["escalated"] + g["open"],
                  "auto_resolved": g["auto"], "escalated": g["escalated"],
                  "unresolved_or_open": g["open"], "samples": len(d),
                  "mean_mttr_s": round(statistics.mean(d), 1) if d else None,
                  "median_mttr_s": round(statistics.median(d), 1) if d else None}
    return out


def print_report(stats):
    print("\nSelf-Healing MTTR Report (measured from audit-log timestamps)")
    print("=" * 78)
    print(f"{'Incident type':<22}{'Inc':>5}{'Auto':>6}{'Esc':>5}{'n':>4}{'Mean s':>9}{'Median s':>10}")
    print("-" * 78)
    for t, s in sorted(stats.items()):
        mean = s["mean_mttr_s"] if s["mean_mttr_s"] is not None else "insufficient data"
        med = s["median_mttr_s"] if s["median_mttr_s"] is not None else "-"
        print(f"{t:<22}{s['incidents']:>5}{s['auto_resolved']:>6}{s['escalated']:>5}"
              f"{s['samples']:>4}{str(mean):>9}{str(med):>10}")
    print("\nMTTR needs >= 1 resolved incident per type; treat n < 30 as indicative only.")


def main():
    ap = argparse.ArgumentParser(description="Self-healing MTTR analyzer")
    ap.add_argument("--log", default=str(AUDIT_LOG))
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    recs = parse_audit_log(Path(a.log))
    if not recs:
        print("No audit records found. Run remediation playbooks first.")
        return
    stats = compute_mttr(recs)
    print(json.dumps(stats, indent=2)) if a.json else print_report(stats)


if __name__ == "__main__":
    main()
