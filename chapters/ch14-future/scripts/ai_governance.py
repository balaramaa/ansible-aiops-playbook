#!/usr/bin/env python3
"""
ai_governance.py — Chapter 14, Listing 14-3
AI governance framework for autonomous infrastructure decisions.

Author : Balaramakrishna Alti
GitHub : https://github.com/balaramaa/ansible-aiops-playbook

Every AI-initiated infrastructure action must pass through this framework.
The framework enforces risk-based approval policies, logs every decision
to a JSONL audit trail, and escalates when human approval is required.

Usage:
    from ai_governance import AIGovernanceFramework, RiskLevel

    governance = AIGovernanceFramework()
    decision   = governance.evaluate(
        action_type="restart_service",
        target_host="node01",
        environment="production",
        context={"incident_id": "INC-001", "service": "nginx"}
    )
    if decision.approved:
        execute_action()
    else:
        escalate_to_human(decision)

    # Generate governance report
    python3 ai_governance.py --report --days 30
"""

import argparse, json, logging, uuid
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

log = logging.getLogger(__name__)

GOVERNANCE_LOG = Path("/var/log/ai_governance_audit.jsonl")


class RiskLevel(str, Enum):
    CRITICAL = "critical"   # Human approval always required regardless of environment
    HIGH     = "high"       # Human approval required in production
    MEDIUM   = "medium"     # Auto in non-prod; human approval in production
    LOW      = "low"        # Auto-approved in all environments
    INFO     = "info"       # Informational; no approval needed


@dataclass
class GovernanceDecision:
    decision_id:     str
    action_type:     str
    target_host:     str
    environment:     str
    risk_level:      str        # RiskLevel value
    approved:        bool
    approval_source: str        # "auto_policy" | "requires_human"
    rationale:       str
    constraints:     list
    audit_trail:     list
    decided_at:      str
    expires_at:      str = None


class AIGovernanceFramework:
    """
    Governance framework for autonomous AI infrastructure decisions.

    Enforces risk-based approval policies that mirror enterprise change
    management processes, ensuring autonomous operations remain within
    organizational risk tolerance — especially in regulated environments.
    """

    # Risk classification by action type
    # Add new action types here as platform capabilities expand
    RISK_MATRIX: dict = {
        # ── Low risk: safe to auto-approve in all environments ────────────
        "clear_page_cache":           RiskLevel.LOW,
        "remove_old_logs":            RiskLevel.LOW,
        "restart_service":            RiskLevel.LOW,
        "reload_config":              RiskLevel.LOW,
        "update_motd":                RiskLevel.LOW,
        "check_compliance":           RiskLevel.LOW,
        "collect_diagnostics":        RiskLevel.INFO,
        "query_metrics":              RiskLevel.INFO,
        "search_logs":                RiskLevel.INFO,

        # ── Medium risk: auto in non-prod; human approval in production ───
        "apply_cis_hardening":        RiskLevel.MEDIUM,
        "apply_patch":                RiskLevel.MEDIUM,
        "update_ssh_config":          RiskLevel.MEDIUM,
        "update_audit_rules":         RiskLevel.MEDIUM,
        "deploy_monitoring_agent":    RiskLevel.MEDIUM,
        "update_cron_job":            RiskLevel.MEDIUM,
        "apply_sysctl_settings":      RiskLevel.MEDIUM,

        # ── High risk: human approval required in production ──────────────
        "rollback_config":            RiskLevel.HIGH,
        "terminate_process":          RiskLevel.HIGH,
        "modify_firewall":            RiskLevel.HIGH,
        "isolate_host":               RiskLevel.HIGH,
        "block_user":                 RiskLevel.HIGH,
        "revoke_ssh_key":             RiskLevel.HIGH,
        "disable_service":            RiskLevel.HIGH,
        "run_playbook":               RiskLevel.HIGH,
        "trigger_eda":                RiskLevel.MEDIUM,

        # ── Critical: human approval always required ───────────────────────
        "shutdown_server":            RiskLevel.CRITICAL,
        "delete_data":                RiskLevel.CRITICAL,
        "network_change":             RiskLevel.CRITICAL,
        "modify_dns":                 RiskLevel.CRITICAL,
        "decommission_host":          RiskLevel.CRITICAL,
        "change_cloud_security_group": RiskLevel.CRITICAL,
    }

    # Maximum risk level that can be auto-approved per environment
    AUTO_APPROVAL_THRESHOLD: dict = {
        "lab":        RiskLevel.HIGH,     # Auto-approve up to HIGH in lab
        "dev":        RiskLevel.HIGH,     # Auto-approve up to HIGH in dev
        "staging":    RiskLevel.MEDIUM,   # Auto-approve up to MEDIUM in staging
        "production": RiskLevel.LOW,      # Only LOW is auto-approved in production
    }

    # Severity order for comparison
    RISK_ORDER = [
        RiskLevel.INFO, RiskLevel.LOW,
        RiskLevel.MEDIUM, RiskLevel.HIGH, RiskLevel.CRITICAL
    ]

    def __init__(self, policy_file: str = None,
                 governance_log:  str = None):
        self.policy        = self._load_policy(policy_file)
        self.governance_log = Path(governance_log or GOVERNANCE_LOG)

    def evaluate(self,
                 action_type:  str,
                 target_host:  str,
                 environment:  str  = "unknown",
                 context:      dict = None) -> GovernanceDecision:
        """
        Evaluate whether an AI-initiated action is approved under governance policy.

        Args:
            action_type:  Type of action from RISK_MATRIX
            target_host:  Target hostname or group
            environment:  Target environment (lab/dev/staging/production)
            context:      Additional context for audit trail

        Returns:
            GovernanceDecision — check .approved before executing action
        """
        risk      = self.RISK_MATRIX.get(action_type, RiskLevel.HIGH)
        threshold = self.AUTO_APPROVAL_THRESHOLD.get(
            environment.lower(), RiskLevel.LOW)

        risk_idx  = self.RISK_ORDER.index(risk)
        thresh_idx = self.RISK_ORDER.index(threshold)
        approved  = risk_idx <= thresh_idx

        # Production-specific additional constraints
        constraints = []
        if environment.lower() == "production":
            constraints.append("ITSM change record required before execution")
            constraints.append("Post-action compliance scan required")
            if risk in (RiskLevel.HIGH, RiskLevel.CRITICAL):
                constraints.append("Senior infrastructure engineer approval required")
                constraints.append("Change advisory board notification required")
                approved = False  # Force human approval for HIGH/CRITICAL in production

        if risk == RiskLevel.CRITICAL:
            approved = False
            constraints.append("CRITICAL risk: human approval always required")

        rationale = (
            f"Action '{action_type}' has risk level {risk.value}. "
            f"Auto-approval threshold for {environment} is {threshold.value}. "
            + ("Approved: risk is within threshold." if approved
               else "Requires human approval: risk exceeds threshold.")
        )

        audit_trail = [
            f"action_type={action_type}",
            f"target={target_host}",
            f"environment={environment}",
            f"risk_level={risk.value}",
            f"threshold={threshold.value}",
            f"approved={approved}",
            f"context={json.dumps(context or {})}",
        ]

        decision = GovernanceDecision(
            decision_id=     str(uuid.uuid4())[:12],
            action_type=     action_type,
            target_host=     target_host,
            environment=     environment,
            risk_level=      risk.value,
            approved=        approved,
            approval_source= "auto_policy" if approved else "requires_human",
            rationale=       rationale,
            constraints=     constraints,
            audit_trail=     audit_trail,
            decided_at=      datetime.now(timezone.utc).isoformat(),
        )

        self._log_decision(decision)

        status = "APPROVED" if approved else "ESCALATION_REQUIRED"
        log.info(
            f"[GOVERNANCE] {status}: {action_type} on {target_host} "
            f"(env={environment}, risk={risk.value})"
        )
        if not approved:
            log.warning(f"  Reason: {rationale}")
            for c in constraints:
                log.warning(f"  Constraint: {c}")

        return decision

    def _log_decision(self, decision: GovernanceDecision) -> None:
        """Append governance decision to JSONL audit log."""
        self.governance_log.parent.mkdir(parents=True, exist_ok=True)
        with self.governance_log.open("a") as f:
            f.write(json.dumps(asdict(decision)) + "\n")

    def _load_policy(self, policy_file: str = None) -> dict:
        """Load custom policy overrides from JSON file."""
        if policy_file and Path(policy_file).exists():
            policy = json.loads(Path(policy_file).read_text())
            # Merge custom risk overrides
            for action, level in policy.get("risk_overrides", {}).items():
                try:
                    self.RISK_MATRIX[action] = RiskLevel(level)
                    log.info(f"Policy override: {action} → {level}")
                except ValueError:
                    log.warning(f"Invalid risk level in policy: {level}")
            return policy
        return {}

    def generate_report(self, days: int = 30) -> dict:
        """Generate governance audit report from JSONL log."""
        from datetime import timedelta
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        decisions = []
        if self.governance_log.exists():
            for line in self.governance_log.read_text().splitlines():
                try:
                    d = json.loads(line)
                    dt = datetime.fromisoformat(d["decided_at"].replace("Z", "+00:00"))
                    if dt >= cutoff:
                        decisions.append(d)
                except (json.JSONDecodeError, KeyError, ValueError):
                    continue

        approved   = [d for d in decisions if d["approved"]]
        escalated  = [d for d in decisions if not d["approved"]]
        by_env     = {}
        by_risk    = {}
        for d in decisions:
            env  = d.get("environment", "unknown")
            risk = d.get("risk_level", "unknown")
            by_env[env]   = by_env.get(env, 0) + 1
            by_risk[risk] = by_risk.get(risk, 0) + 1

        return {
            "period_days":        days,
            "generated_at":       datetime.now(timezone.utc).isoformat(),
            "total_decisions":    len(decisions),
            "auto_approved":      len(approved),
            "escalated":          len(escalated),
            "auto_approval_rate": f"{len(approved)/max(len(decisions),1)*100:.1f}%",
            "by_environment":     by_env,
            "by_risk_level":      by_risk,
            "top_escalations":    [
                {"action": d["action_type"], "host": d["target_host"],
                 "risk": d["risk_level"], "rationale": d["rationale"]}
                for d in escalated[-10:]
            ],
        }


def main():
    parser = argparse.ArgumentParser(description="AI Governance Framework")
    parser.add_argument("--test",        action="store_true",
                        help="Run test evaluations across risk levels and environments")
    parser.add_argument("--report",      action="store_true",
                        help="Generate governance audit report")
    parser.add_argument("--days",        type=int, default=30)
    parser.add_argument("--json",        action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s")

    framework = AIGovernanceFramework()

    if args.test:
        print("\nGovernance Framework Test Evaluations")
        print("="*60)
        test_cases = [
            ("restart_service",   "node01", "production"),
            ("restart_service",   "node01", "lab"),
            ("apply_cis_hardening","node02","production"),
            ("apply_cis_hardening","node02","staging"),
            ("rollback_config",   "node03", "production"),
            ("isolate_host",      "node04", "production"),
            ("shutdown_server",   "node05", "lab"),
            ("run_playbook",      "node06", "staging"),
        ]
        for action, host, env in test_cases:
            d = framework.evaluate(action, host, env,
                                   context={"test": True})
            status = "✔ AUTO" if d.approved else "✗ HUMAN"
            print(f"  [{status}] {action:<30} {env:<12} risk={d.risk_level}")

    elif args.report:
        report = framework.generate_report(args.days)
        if args.json:
            print(json.dumps(report, indent=2))
        else:
            print(f"\nAI Governance Audit Report — Last {args.days} Days")
            print(f"{'='*50}")
            print(f"Total decisions   : {report['total_decisions']}")
            print(f"Auto-approved     : {report['auto_approved']} ({report['auto_approval_rate']})")
            print(f"Escalated         : {report['escalated']}")
            print(f"\nBy environment    : {report['by_environment']}")
            print(f"By risk level     : {report['by_risk_level']}")


if __name__ == "__main__":
    main()
