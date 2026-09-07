#!/usr/bin/env python3
"""
patch_orchestrator.py — Chapter 6, Listing 6-7
The predictive patch governance orchestrator.

Author : Balaramakrishna Alti
GitHub : https://github.com/balaramaa/ansible-aiops-playbook

Usage:
    python3 patch_orchestrator.py --group lab --mock --dry-run
    python3 patch_orchestrator.py --group prod_web --execute
"""

import argparse, json, logging, os, subprocess
from datetime import datetime, timezone
from pathlib import Path

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

PATCH_AUDIT_LOG = Path("/var/log/patch_governance_audit.jsonl")
TOTAL_HOSTS     = int(os.environ.get("TOTAL_HOST_COUNT", "4500"))


def build_patch_plan(host_group: str,
                     business_tier: str = "standard",
                     mock: bool = False) -> list:
    """
    Build a prioritized patch plan for a host group.

    Returns list of patch actions sorted by risk score (highest first).
    """
    from satellite_client import SatelliteClient
    from cve_risk_scorer  import CVERiskScore
    from nvd_client       import get_cve_details, is_exploited
    from window_optimizer import recommend_windows

    satellite = SatelliteClient(mock=mock)
    errata    = satellite.get_applicable_errata()

    log.info(f"Scoring {len(errata)} errata for {host_group}")
    patch_plan = []

    for erratum in errata:
        if erratum.errata_type != "security":
            continue

        max_score   = 0.0
        primary_cve = None

        for cve_id in erratum.cves:
            try:
                if mock:
                    details   = {"cvss_score": 7.5, "days_since_pub": 14}
                    exploited = cve_id.endswith("4")  # Mock: some CVEs exploited
                else:
                    details   = get_cve_details(cve_id)
                    exploited = is_exploited(cve_id)
            except Exception as e:
                log.warning(f"Could not fetch {cve_id}: {e}")
                details, exploited = {"cvss_score": 0.0, "days_since_pub": 0}, False

            scorer = CVERiskScore(
                cve_id=cve_id,
                cvss_base=details.get("cvss_score", 0.0),
                exploit_available=exploited,
                affected_hosts=erratum.hosts_count,
                total_hosts=TOTAL_HOSTS,
                business_tier=business_tier,
                days_since_pub=details.get("days_since_pub", 0),
            ).compute()

            if scorer.risk_score > max_score:
                max_score   = scorer.risk_score
                primary_cve = scorer

        if primary_cve:
            windows = recommend_windows(host_group, primary_cve.risk_tier,
                                        n=3, mock=mock)
            patch_plan.append({
                "errata_id":    erratum.errata_id,
                "title":        erratum.title,
                "severity":     erratum.severity,
                "hosts":        erratum.hosts_count,
                "risk_score":   primary_cve.risk_score,
                "risk_tier":    primary_cve.risk_tier,
                "sla_hours":    primary_cve.patch_sla_hours,
                "auto_approve": primary_cve.auto_approve,
                "top_cve":      primary_cve.cve_id,
                "windows":      windows,
            })

    patch_plan.sort(key=lambda x: x["risk_score"], reverse=True)
    log.info(
        f"Patch plan: {len(patch_plan)} items, "
        f"top score: {patch_plan[0]['risk_score'] if patch_plan else 0}"
    )
    return patch_plan


def execute_patch(patch_item: dict,
                  host_group: str,
                  dry_run: bool = True) -> dict:
    """Execute a single patch item via the canary playbook."""
    if not patch_item["auto_approve"] and not dry_run:
        log.warning(
            f"Manual approval required: {patch_item['errata_id']} "
            f"(risk: {patch_item['risk_tier']})"
        )
        return {"status": "awaiting_approval", **patch_item}

    cmd = [
        "ansible-playbook",
        "-i", "inventory/",
        "--limit", host_group,
        "-e", json.dumps({
            "errata_ids":   [patch_item["errata_id"]],
            "target_group": host_group,
            "risk_tier":    patch_item["risk_tier"],
        }),
        "playbooks/patch_canary.yml",
    ]
    if dry_run:
        cmd += ["--check", "--diff"]

    result = subprocess.run(cmd, capture_output=True, text=True)

    outcome = {
        **patch_item,
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "dry_run":     dry_run,
        "status":      "success" if result.returncode == 0 else "failed",
        "host_group":  host_group,
    }

    PATCH_AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
    with PATCH_AUDIT_LOG.open("a") as f:
        f.write(json.dumps(outcome) + "\n")

    return outcome


def main():
    parser = argparse.ArgumentParser(
        description="Predictive patch governance orchestrator"
    )
    parser.add_argument("--group",    required=True, help="Host group")
    parser.add_argument("--tier",     default="standard",
                        choices=["critical","high","standard","low"])
    parser.add_argument("--mock",     action="store_true",
                        help="Use mock data (no Satellite/NVD API calls)")
    parser.add_argument("--dry-run",  action="store_true", default=True)
    parser.add_argument("--execute",  action="store_true",
                        help="Execute patches (removes --dry-run)")
    args = parser.parse_args()

    dry_run = not args.execute
    plan    = build_patch_plan(args.group, args.tier, args.mock)

    if not plan:
        print("No applicable security errata found.")
        return

    # Print plan table
    print(f"\nPatch Plan for '{args.group}' ({len(plan)} items):")
    print(f"{'─'*72}")
    print(f"{'Errata ID':<20} {'Score':>6} {'Tier':<10} {'SLA':>5}h  {'Auto'}  Title")
    print(f"{'─'*72}")
    for item in plan:
        auto = "✔" if item["auto_approve"] else "✗"
        print(
            f"{item['errata_id']:<20} {item['risk_score']:>6.1f} "
            f"{item['risk_tier']:<10} {item['sla_hours']:>5}  {auto}    "
            f"{item['title'][:30]}"
        )

    if dry_run:
        print(f"\n[DRY RUN] Use --execute to apply patches")
        return

    print(f"\nExecuting auto-approved patches...")
    for item in plan:
        if item["auto_approve"]:
            result = execute_patch(item, args.group, dry_run=False)
            icon   = "✔" if result["status"] == "success" else "✗"
            print(f"  {icon} {item['errata_id']} — {result['status']}")


if __name__ == "__main__":
    main()
