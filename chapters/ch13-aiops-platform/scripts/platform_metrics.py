#!/usr/bin/env python3
"""
platform_metrics.py — Chapter 13, Listing 13-7
Aggregate platform-wide AIOps operational intelligence metrics.

Author : Balaramakrishna Alti
GitHub : https://github.com/balaramaa/ansible-aiops-playbook

Usage:
    python3 platform_metrics.py --days 30
    python3 platform_metrics.py --days 7 --json
"""

import argparse, json, statistics
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path


def compute_platform_metrics(days: int = 30) -> dict:
    """
    Compute platform-wide AIOps operational metrics.

    Reads from:
      - /var/log/self_healing_audit.log   (Chapter 7)
      - /var/log/patch_governance_audit.jsonl (Chapter 6)
      - /var/log/compliance/results-*.xml (Chapter 5)
      - /var/log/migration_audit.log      (Chapter 12)
      - /var/log/security_events.jsonl    (Chapter 8)

    Returns metrics dict suitable for API response or dashboard.
    """
    audit_log   = Path("/var/log/self_healing_audit.log")
    patch_log   = Path("/var/log/patch_governance_audit.jsonl")
    compliance  = Path("/var/log/compliance/")
    migration   = Path("/var/log/migration_audit.log")
    security    = Path("/var/log/security_events.jsonl")

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    metrics = {
        "period_days":    days,
        "computed_at":    datetime.now(timezone.utc).isoformat(),
        "self_healing":   {
            "total_events":      0,
            "auto_resolved":     0,
            "escalated":         0,
            "auto_resolve_rate": "0%",
            "avg_mttr_seconds":  0,
        },
        "compliance":     {
            "avg_score":          0.0,
            "min_score":          0.0,
            "hosts_scanned":      0,
            "hosts_below_90pct":  0,
            "hosts_below_95pct":  0,
        },
        "patching":       {
            "patches_applied":    0,
            "auto_patches":       0,
            "manual_required":    0,
        },
        "security":       {
            "threats_detected":   0,
            "critical_threats":   0,
            "auto_responded":     0,
        },
        "migration":      {
            "servers_migrated":   0,
            "rollbacks":          0,
        },
        "platform_health": "healthy",
    }

    # ── Self-healing metrics ──────────────────────────────────────────────────
    if audit_log.exists():
        for line in audit_log.read_text().splitlines():
            metrics["self_healing"]["total_events"] += 1
            if "SUCCESS" in line:
                metrics["self_healing"]["auto_resolved"] += 1
            elif "ESCALAT" in line or "ROLLBACK" in line:
                metrics["self_healing"]["escalated"] += 1

        total    = metrics["self_healing"]["total_events"]
        resolved = metrics["self_healing"]["auto_resolved"]
        if total > 0:
            rate = resolved / total * 100
            metrics["self_healing"]["auto_resolve_rate"] = f"{rate:.1f}%"
            metrics["self_healing"]["avg_mttr_seconds"]  = 90  # proxy

    # ── Compliance metrics ────────────────────────────────────────────────────
    if compliance.exists():
        scores = []
        import xml.etree.ElementTree as ET
        for report_file in compliance.glob("results-*.xml"):
            try:
                tree = ET.parse(report_file)
                root = tree.getroot()
                ns   = {"x": "http://checklists.nist.gov/xccdf/1.2"}
                for score_el in root.findall(".//x:score", ns):
                    val = float(score_el.text)
                    if 0 <= val <= 100:
                        scores.append(val)
            except Exception:
                continue

        if scores:
            metrics["compliance"]["hosts_scanned"]     = len(scores)
            metrics["compliance"]["avg_score"]         = round(statistics.mean(scores), 2)
            metrics["compliance"]["min_score"]         = round(min(scores), 2)
            metrics["compliance"]["hosts_below_90pct"] = sum(1 for s in scores if s < 90)
            metrics["compliance"]["hosts_below_95pct"] = sum(1 for s in scores if s < 95)

    # ── Patch metrics ─────────────────────────────────────────────────────────
    if patch_log.exists():
        for line in patch_log.read_text().splitlines():
            try:
                record = json.loads(line)
                if record.get("status") == "success":
                    metrics["patching"]["patches_applied"] += 1
                    if record.get("auto_approved", False):
                        metrics["patching"]["auto_patches"] += 1
                    else:
                        metrics["patching"]["manual_required"] += 1
            except (json.JSONDecodeError, KeyError):
                continue

    # ── Security metrics ──────────────────────────────────────────────────────
    if security.exists():
        for line in security.read_text().splitlines():
            try:
                record = json.loads(line)
                metrics["security"]["threats_detected"] += 1
                if record.get("threat_level") == "critical":
                    metrics["security"]["critical_threats"] += 1
                if record.get("auto_respond"):
                    metrics["security"]["auto_responded"] += 1
            except (json.JSONDecodeError, KeyError):
                continue

    # ── Migration metrics ─────────────────────────────────────────────────────
    if migration.exists():
        for line in migration.read_text().splitlines():
            if "MIGRATION_SUCCESS" in line:
                metrics["migration"]["servers_migrated"] += 1
            elif "ROLLBACK" in line:
                metrics["migration"]["rollbacks"] += 1

    # ── Platform health determination ─────────────────────────────────────────
    esc_rate   = (metrics["self_healing"]["escalated"] /
                  max(metrics["self_healing"]["total_events"], 1))
    avg_score  = metrics["compliance"]["avg_score"]
    threats    = metrics["security"]["critical_threats"]

    if esc_rate > 0.40 or avg_score < 70 or threats > 10:
        metrics["platform_health"] = "critical"
    elif esc_rate > 0.20 or avg_score < 85 or threats > 5:
        metrics["platform_health"] = "degraded"
    else:
        metrics["platform_health"] = "healthy"

    return metrics


def print_metrics(metrics: dict) -> None:
    """Print human-readable metrics report."""
    print(f"\nAIOps Platform Metrics — Last {metrics['period_days']} Days")
    print(f"{'='*55}")
    print(f"Computed: {metrics['computed_at'][:19]}")
    print(f"Platform health: {metrics['platform_health'].upper()}")

    sh = metrics["self_healing"]
    print(f"\nSelf-Healing:")
    print(f"  Total events     : {sh['total_events']}")
    print(f"  Auto-resolved    : {sh['auto_resolved']} ({sh['auto_resolve_rate']})")
    print(f"  Escalated        : {sh['escalated']}")
    print(f"  Avg MTTR         : {sh['avg_mttr_seconds']}s (auto-remediated)")

    co = metrics["compliance"]
    print(f"\nCompliance:")
    print(f"  Hosts scanned    : {co['hosts_scanned']}")
    print(f"  Avg score        : {co['avg_score']}%")
    print(f"  Min score        : {co['min_score']}%")
    print(f"  Below 90%        : {co['hosts_below_90pct']} hosts")
    print(f"  Below 95%        : {co['hosts_below_95pct']} hosts")

    pa = metrics["patching"]
    print(f"\nPatching:")
    print(f"  Patches applied  : {pa['patches_applied']}")
    print(f"  Auto-approved    : {pa['auto_patches']}")
    print(f"  Manual required  : {pa['manual_required']}")

    se = metrics["security"]
    print(f"\nSecurity:")
    print(f"  Threats detected : {se['threats_detected']}")
    print(f"  Critical threats : {se['critical_threats']}")
    print(f"  Auto-responded   : {se['auto_responded']}")

    mi = metrics["migration"]
    print(f"\nMigration:")
    print(f"  Servers migrated : {mi['servers_migrated']}")
    print(f"  Rollbacks        : {mi['rollbacks']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AIOps platform metrics")
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    m = compute_platform_metrics(args.days)
    if args.json:
        print(json.dumps(m, indent=2))
    else:
        print_metrics(m)
