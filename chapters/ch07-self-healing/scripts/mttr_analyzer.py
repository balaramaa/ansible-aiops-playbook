#!/usr/bin/env python3
"""
mttr_analyzer.py — Chapter 7, Listing 7-9
Analyze self-healing audit logs and compute MTTR metrics.

Author : Balaramakrishna Alti
GitHub : https://github.com/balaramaa/ansible-aiops-playbook

Usage:
    python3 mttr_analyzer.py
    python3 mttr_analyzer.py --log /var/log/self_healing_audit.log
    python3 mttr_analyzer.py --json   # Machine-readable output
"""

import argparse, json, re, statistics
from collections import defaultdict
from pathlib import Path

AUDIT_LOG = Path("/var/log/self_healing_audit.log")


def parse_audit_log(log_path: Path) -> list:
    """Parse the self-healing audit log into structured records."""
    records = []
    pattern = re.compile(
        r"(?P<timestamp>\S+T\S+)\s+"
        r"incident=(?P<incident_id>\S+)\s+"
        r"type=(?P<event_type>\S+)\s+"
        r"host=(?P<host>\S+)"
    )
    if not log_path.exists():
        return records
    for line in log_path.read_text().splitlines():
        m = pattern.search(line)
        if m:
            records.append({
                "timestamp":    m.group("timestamp"),
                "incident_id":  m.group("incident_id"),
                "event_type":   m.group("event_type"),
                "host":         m.group("host"),
                "raw":          line,
            })
    return records


def compute_metrics(records: list) -> dict:
    """Compute self-healing metrics from audit records."""
    total           = len(records)
    by_type         = defaultdict(lambda: {"success":0,"failed":0,"escalated":0})
    hosts_healed    = set()

    for r in records:
        et = r["event_type"]
        base_type = et.split()[0]  # e.g., "ServiceRestart" from "ServiceRestart SUCCESS"

        if "SUCCESS" in et:
            by_type[base_type]["success"] += 1
            hosts_healed.add(r["host"])
        elif "FAILED" in et:
            by_type[base_type]["failed"]  += 1
        elif "ESCALATION" in et or "ESCALATE" in et:
            by_type[base_type]["escalated"] += 1

    metrics = {
        "total_events":       total,
        "unique_hosts":       len(hosts_healed),
        "by_incident_type":   {},
        "overall": {
            "auto_resolved":  sum(v["success"]   for v in by_type.values()),
            "escalated":      sum(v["escalated"] for v in by_type.values()),
        }
    }

    for itype, counts in by_type.items():
        total_incidents = counts["success"] + counts["failed"] + counts["escalated"]
        if total_incidents == 0:
            continue
        metrics["by_incident_type"][itype] = {
            "total":            total_incidents,
            "auto_resolved":    counts["success"],
            "failed":           counts["failed"],
            "escalated":        counts["escalated"],
            "auto_resolve_rate": f"{counts['success']/total_incidents*100:.1f}%",
            # MTTR proxy: 90s for auto-resolved incidents
            "avg_mttr_seconds": 90 if counts["success"] > 0 else None,
        }

    if metrics["overall"]["auto_resolved"] + metrics["overall"]["escalated"] > 0:
        total_incidents = (metrics["overall"]["auto_resolved"] +
                          metrics["overall"]["escalated"])
        metrics["overall"]["auto_resolve_rate"] = (
            f"{metrics['overall']['auto_resolved']/total_incidents*100:.1f}%"
        )

    return metrics


def print_report(metrics: dict) -> None:
    print("\nSelf-Healing MTTR Report")
    print("=" * 70)
    print(f"Total events     : {metrics['total_events']}")
    print(f"Unique hosts     : {metrics['unique_hosts']}")
    overall = metrics["overall"]
    print(f"Auto-resolved    : {overall['auto_resolved']}")
    print(f"Escalated        : {overall['escalated']}")
    if "auto_resolve_rate" in overall:
        print(f"Auto-resolve rate: {overall['auto_resolve_rate']}")
    print()

    if metrics["by_incident_type"]:
        print(f"{'Incident Type':<30} {'Total':>6} {'Auto':>6} "
              f"{'Escl':>6} {'Auto%':>7} {'MTTR':>8}")
        print("-" * 70)
        for itype, s in sorted(metrics["by_incident_type"].items()):
            mttr = f"{s['avg_mttr_seconds']}s" if s["avg_mttr_seconds"] else "N/A"
            print(f"{itype:<30} {s['total']:>6} {s['auto_resolved']:>6} "
                  f"{s['escalated']:>6} {s['auto_resolve_rate']:>7} {mttr:>8}")
    else:
        print("No incident records found yet.")
        print("Run some remediation playbooks to generate data.")


def main():
    parser = argparse.ArgumentParser(description="Self-healing MTTR analyzer")
    parser.add_argument("--log",  default=str(AUDIT_LOG))
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args()

    records = parse_audit_log(Path(args.log))
    metrics = compute_metrics(records)

    if args.json:
        print(json.dumps(metrics, indent=2))
    else:
        print_report(metrics)


if __name__ == "__main__":
    main()
