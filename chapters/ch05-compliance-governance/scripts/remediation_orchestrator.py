#!/usr/bin/env python3
"""
remediation_orchestrator.py — Chapter 5, Listing 5-8
Orchestrates automated compliance remediation based on AI classification.

Author : Balaramakrishna Alti
GitHub : https://github.com/balaramaa/ansible-aiops-playbook

Usage:
    python3 remediation_orchestrator.py --host node01 --dry-run
    python3 remediation_orchestrator.py --host node01 --execute
"""

import argparse, json, logging, subprocess
from datetime import datetime, timezone
from pathlib import Path

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

REMEDIATION_PLAYBOOK = "playbooks/compliance_remediate.yml"
AUDIT_LOG            = Path("/var/log/compliance/remediation_audit.jsonl")


def remediate(hostname: str,
              classification: dict,
              inventory: str = "inventory/",
              dry_run: bool = True) -> dict:
    """
    Execute compliance remediation for a host.

    Args:
        hostname:       Target host
        classification: AI classification from drift_classifier.py
        inventory:      Ansible inventory path
        dry_run:        If True, use --check mode only

    Returns:
        Remediation result dict
    """
    if not classification.get("auto_remediate"):
        log.warning(
            f"Auto-remediation NOT approved for {hostname} "
            f"(risk: {classification.get('risk_level','unknown')}). "
            f"Reason: {classification.get('auto_remediate_rationale','N/A')}"
        )
        return {
            "hostname": hostname,
            "status":   "awaiting_approval",
            "reason":   "requires_human_approval",
            "risk_level": classification.get("risk_level"),
        }

    log.info(
        f"Starting {'DRY RUN ' if dry_run else ''}remediation "
        f"for {hostname} (risk: {classification.get('risk_level')})"
    )

    extra_vars = {
        "remediation_id":       datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S"),
        "risk_level":           classification.get("risk_level","medium"),
        "recommended_action":   classification.get("recommended_action","apply_cis_baseline"),
    }

    cmd = [
        "ansible-playbook",
        "-i", inventory,
        "--limit", hostname,
        "-e", json.dumps(extra_vars),
        REMEDIATION_PLAYBOOK,
    ]
    if dry_run:
        cmd += ["--check", "--diff"]

    result = subprocess.run(cmd, capture_output=True, text=True)

    outcome = {
        "hostname":           hostname,
        "timestamp":          datetime.now(timezone.utc).isoformat(),
        "status":             "success" if result.returncode == 0 else "failed",
        "exit_code":          result.returncode,
        "dry_run":            dry_run,
        "risk_level":         classification.get("risk_level"),
        "recommended_action": classification.get("recommended_action"),
        "remediation_id":     extra_vars["remediation_id"],
    }

    # Append to audit log (JSONL — one record per line)
    AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
    with AUDIT_LOG.open("a") as f:
        f.write(json.dumps(outcome) + "\n")

    if outcome["status"] == "success":
        log.info(f"✔ Remediation {'(dry run) ' if dry_run else ''}successful: {hostname}")
    else:
        log.error(f"✗ Remediation failed: {hostname} (rc={result.returncode})")
        log.error(f"  stderr: {result.stderr[:500]}")

    return outcome


def main():
    parser = argparse.ArgumentParser(
        description="Compliance remediation orchestrator"
    )
    parser.add_argument("--host",       required=True, help="Target hostname")
    parser.add_argument("--inventory",  default="inventory/")
    parser.add_argument("--risk-level", default="medium",
                        choices=["critical","high","medium","low"])
    parser.add_argument("--dry-run",  action="store_true", default=True)
    parser.add_argument("--execute",  action="store_true",
                        help="Execute remediation (removes --dry-run)")
    args = parser.parse_args()

    dry_run = not args.execute

    # Build a minimal classification dict for standalone use
    classification = {
        "risk_level":             args.risk_level,
        "auto_remediate":         args.risk_level in ("medium","low"),
        "auto_remediate_rationale": (
            "Automated remediation safe for medium/low risk"
            if args.risk_level in ("medium","low")
            else "High/critical risk requires human approval"
        ),
        "recommended_action":     "apply_cis_baseline",
    }

    result = remediate(
        hostname=args.host,
        classification=classification,
        inventory=args.inventory,
        dry_run=dry_run,
    )
    print(json.dumps(result, indent=2))
    if result["status"] == "failed":
        exit(1)


if __name__ == "__main__":
    main()
