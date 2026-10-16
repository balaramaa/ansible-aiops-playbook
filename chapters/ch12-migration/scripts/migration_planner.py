#!/usr/bin/env python3
"""
migration_planner.py — Chapter 12, Listing 12-3
Generate migration batch plan from readiness assessment results.

Author : Balaramakrishna Alti
GitHub : https://github.com/balaramaa/ansible-aiops-playbook

Usage:
    python3 migration_planner.py \
        --assessment /tmp/assessment_results.json \
        --batch-size 50 \
        --start-date 2024-10-15

    python3 migration_planner.py \
        --assessment /tmp/assessment_results.json \
        --batch-size 10 \
        --start-date $(date +%Y-%m-%d) \
        --json
"""

import argparse, json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta
from pathlib import Path


@dataclass
class MigrationBatch:
    batch_id:         str
    batch_number:     int
    category:         str
    hosts:            list
    host_count:       int
    estimated_hours:  float
    start_date:       str
    maintenance_window: str
    rationale:        str
    pre_checks:       list = field(default_factory=list)
    rollback_trigger: str  = "compliance_score < 90"


def generate_migration_plan(assessment_file: str,
                             start_date:      str = None,
                             batch_size:      int = 50,
                             window_days:     list = None) -> list:
    """
    Generate sequenced migration batches from assessment results.

    Batch sequencing:
      BATCH-00-PILOT    : Top 10 highest-readiness servers (validate process)
      BATCH-01..N       : Remaining 'ready' servers in batch_size groups
      BATCH-xx-REMEDIATE: 'needs_remediation' servers (after blockers resolved)
      Manual review servers excluded (listed in plan summary)
    """
    reports = json.loads(Path(assessment_file).read_text())
    windows = window_days or [5, 6]  # Sat=5, Sun=6 by default

    if start_date:
        start = datetime.strptime(start_date, "%Y-%m-%d").replace(
            tzinfo=timezone.utc)
    else:
        start = datetime.now(timezone.utc)

    # Sort ready servers: highest score first, then by recommended_batch
    batch_order = {"early": 0, "mid": 1, "late": 2}
    ready    = sorted(
        [r for r in reports if r.get("category") == "ready"],
        key=lambda r: (batch_order.get(r.get("recommended_batch","late"),2),
                       -r.get("readiness_score", 0))
    )
    remediate = [r for r in reports if r.get("category") == "needs_remediation"]
    manual    = [r for r in reports if r.get("category") == "manual_review"]

    batches      = []
    batch_num    = 0
    current_date = start

    def next_window(dt: datetime) -> datetime:
        """Advance to next maintenance window day."""
        while dt.weekday() not in windows:
            dt += timedelta(days=1)
        return dt

    def window_label(dt: datetime) -> str:
        days = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"]
        return f"{days[dt.weekday()]} {dt.strftime('%Y-%m-%d')} 00:00-06:00 UTC"

    # ── Pilot batch ────────────────────────────────────────────────────────
    pilot_candidates = [r for r in ready if r.get("readiness_score", 0) >= 90][:10]
    if not pilot_candidates and ready:
        pilot_candidates = ready[:5]  # Take first 5 if none score 90+

    if pilot_candidates:
        window = next_window(current_date)
        batches.append(MigrationBatch(
            batch_id=          "BATCH-00-PILOT",
            batch_number=      0,
            category=          "pilot",
            hosts=             [r["hostname"] for r in pilot_candidates],
            host_count=        len(pilot_candidates),
            estimated_hours=   sum(r.get("estimated_migration_hours", 2.0)
                                   for r in pilot_candidates),
            start_date=        window.strftime("%Y-%m-%d"),
            maintenance_window=window_label(window),
            rationale=         (f"Pilot batch: {len(pilot_candidates)} highest-readiness "
                                f"servers (score ≥90) to validate migration process"),
            pre_checks=[
                "Verify Ansible connectivity to all pilot hosts (ansible -m ping)",
                "Confirm rollback procedure tested on non-production host",
                "Notify application owners 48 hours in advance",
                "Ensure Prometheus and Grafana are running for real-time monitoring",
            ],
        ))
        current_date = window + timedelta(days=7)
        batch_num    = 1
        ready        = [r for r in ready if r not in pilot_candidates]

    # ── Ready batches ──────────────────────────────────────────────────────
    for i in range(0, len(ready), batch_size):
        batch_hosts = ready[i:i + batch_size]
        window = next_window(current_date)
        batches.append(MigrationBatch(
            batch_id=          f"BATCH-{batch_num:02d}",
            batch_number=      batch_num,
            category=          "ready",
            hosts=             [r["hostname"] for r in batch_hosts],
            host_count=        len(batch_hosts),
            estimated_hours=   sum(r.get("estimated_migration_hours", 2.0)
                                   for r in batch_hosts),
            start_date=        window.strftime("%Y-%m-%d"),
            maintenance_window=window_label(window),
            rationale=         (f"Ready servers batch {batch_num}: "
                                f"{len(batch_hosts)} servers"),
        ))
        current_date = window + timedelta(days=7)
        batch_num   += 1

    # ── Post-remediation batches ───────────────────────────────────────────
    if remediate:
        # Allow 2-week remediation window before scheduling
        current_date += timedelta(days=14)
        for i in range(0, len(remediate), batch_size):
            batch_hosts = remediate[i:i + batch_size]
            window = next_window(current_date)
            batches.append(MigrationBatch(
                batch_id=          f"BATCH-{batch_num:02d}-REMEDIATE",
                batch_number=      batch_num,
                category=          "needs_remediation",
                hosts=             [r["hostname"] for r in batch_hosts],
                host_count=        len(batch_hosts),
                estimated_hours=   sum(r.get("estimated_migration_hours", 4.0)
                                       for r in batch_hosts),
                start_date=        window.strftime("%Y-%m-%d"),
                maintenance_window=window_label(window),
                rationale=         (f"Post-remediation batch {batch_num}: "
                                    f"{len(batch_hosts)} servers (blockers must be "
                                    f"resolved before this batch executes)"),
                pre_checks=[
                    "Re-run migration_assessor.py to confirm all blockers resolved",
                    "Verify readiness_score >= 80 for all hosts in this batch",
                    "Review auto_fixable blockers — apply remediation playbook if needed",
                ],
            ))
            current_date = window + timedelta(days=7)
            batch_num   += 1

    return batches, manual


def print_plan(batches: list, manual: list) -> None:
    total_hosts = sum(b.host_count for b in batches)
    total_hrs   = sum(b.estimated_hours for b in batches)
    last_date   = batches[-1].start_date if batches else "N/A"

    print(f"\nMigration Execution Plan")
    print(f"{'='*65}")
    print(f"Total batches          : {len(batches)}")
    print(f"Total servers in plan  : {total_hosts}")
    print(f"Manual review excluded : {len(manual)}")
    print(f"Estimated total effort : {total_hrs:.0f} hours")
    print(f"Projected completion   : {last_date} (+ validation week)")
    print()

    for b in batches:
        print(f"{'─'*65}")
        print(f"  {b.batch_id}  [{b.category.upper()}]")
        print(f"  Window     : {b.maintenance_window}")
        print(f"  Hosts      : {b.host_count} servers")
        print(f"  Est. hours : {b.estimated_hours:.1f}h")
        print(f"  Rationale  : {b.rationale}")
        if b.pre_checks:
            print(f"  Pre-checks :")
            for pc in b.pre_checks:
                print(f"    • {pc}")

    if manual:
        print(f"\n{'='*65}")
        print(f"Excluded — Manual Review Required ({len(manual)} servers):")
        for r in manual:
            print(f"  • {r['hostname']}: {r.get('summary','')}")


def main():
    parser = argparse.ArgumentParser(
        description="Migration batch planner"
    )
    parser.add_argument("--assessment",  required=True,
                        help="Path to assessment results JSON")
    parser.add_argument("--batch-size",  type=int, default=50)
    parser.add_argument("--start-date",  default=None,
                        help="Migration start date (YYYY-MM-DD)")
    parser.add_argument("--windows",     nargs="+", type=int,
                        default=[5, 6],
                        help="Maintenance window weekdays (0=Mon, 5=Sat, 6=Sun)")
    parser.add_argument("--json",        action="store_true")
    args = parser.parse_args()

    batches, manual = generate_migration_plan(
        args.assessment,
        start_date=args.start_date,
        batch_size=args.batch_size,
        window_days=args.windows,
    )

    if args.json:
        print(json.dumps({
            "batches": [asdict(b) for b in batches],
            "manual_review": manual,
        }, indent=2))
    else:
        print_plan(batches, manual)


if __name__ == "__main__":
    main()
