#!/usr/bin/env python3
"""
cve_risk_scorer.py — Chapter 6, Listing 6-2
Five-dimension CVE risk scoring model.

Based on: Alti, B. (2024). Predictive Risk-Aware Patch Governance Using
Artificial Intelligence. Contemporary Readings in Law and Social Justice.

Author : Balaramakrishna Alti
GitHub : https://github.com/balaramaa/ansible-aiops-playbook

Usage:
    python3 cve_risk_scorer.py --cve CVE-2024-1234 --affected-hosts 847 \
        --total-hosts 4500 --tier standard

    # Or use as a library:
    from cve_risk_scorer import CVERiskScore
    score = CVERiskScore(
        cve_id="CVE-2024-1234",
        cvss_base=9.8,
        exploit_available=True,
        affected_hosts=847,
        total_hosts=4500,
        business_tier="standard",
        days_since_pub=14,
    ).compute()
    print(f"Risk: {score.risk_score}/100 ({score.risk_tier})")
    print(f"SLA: {score.patch_sla_hours}h | Auto: {score.auto_approve}")
"""

import argparse, json, logging, sys
from dataclasses import dataclass

log = logging.getLogger(__name__)


@dataclass
class CVERiskScore:
    """
    Five-dimension CVE risk scoring model.

    Dimensions (with weights from published research):
      - CVSS base score      (30%): Theoretical maximum severity
      - Exploit availability (25%): Public exploit or CISA KEV membership
      - Asset exposure       (20%): % of fleet affected + network exposure
      - Business criticality (15%): Business tier of affected systems
      - Temporal factor      (10%): Days since publication (risk grows over time)
    """

    # Input dimensions
    cve_id:            str
    cvss_base:         float   # 0.0 - 10.0
    exploit_available: bool    # True if in CISA KEV or Metasploit
    affected_hosts:    int     # Number of hosts needing the patch
    total_hosts:       int     # Total managed hosts (denominator for exposure)
    business_tier:     str     # critical | high | standard | low
    days_since_pub:    int     # Days since CVE publication

    # Computed outputs (populated by .compute())
    risk_score:        float = 0.0
    risk_tier:         str   = ""     # critical | high | medium | low
    patch_sla_hours:   int   = 0      # Hours to patch per SLA
    auto_approve:      bool  = False  # Safe for automated patching?

    # Dimension weights (sum to 1.0)
    W_CVSS:        float = 0.30
    W_EXPLOIT:     float = 0.25
    W_EXPOSURE:    float = 0.20
    W_CRITICALITY: float = 0.15
    W_TEMPORAL:    float = 0.10

    def compute(self) -> "CVERiskScore":
        """Compute the composite risk score from all five dimensions."""

        # ── Dimension 1: CVSS (normalized to 0-100) ─────────────────────
        cvss_score = (self.cvss_base / 10.0) * 100

        # ── Dimension 2: Exploit availability ───────────────────────────
        # CISA KEV = 100 (actively exploited in wild)
        # Metasploit/ExploitDB = 80 (public exploit exists)
        # No public exploit = 20 (theoretical only)
        exploit_score = 100 if self.exploit_available else 20

        # ── Dimension 3: Asset exposure ──────────────────────────────────
        # Percentage of fleet affected, scaled to 0-100
        # Cap at 100 (more than 50% of fleet = max exposure score)
        exposure_pct  = (self.affected_hosts / max(self.total_hosts, 1)) * 100
        exposure_score = min(exposure_pct * 2, 100)

        # ── Dimension 4: Business criticality ───────────────────────────
        tier_scores = {
            "critical": 100,   # Financial core, payment processing, PII
            "high":      75,   # Customer-facing, internal APIs
            "standard":  40,   # Standard enterprise systems
            "low":       15,   # Development, test, non-sensitive
        }
        crit_score = tier_scores.get(self.business_tier, 40)

        # ── Dimension 5: Temporal factor ─────────────────────────────────
        # Risk grows linearly over time, reaching max at 90 days
        # After 90 days unpatched, adversaries have had time to integrate
        temporal_score = min((self.days_since_pub / 90.0) * 100, 100)

        # ── Composite score ───────────────────────────────────────────────
        self.risk_score = round(
            (cvss_score    * self.W_CVSS)        +
            (exploit_score * self.W_EXPLOIT)     +
            (exposure_score * self.W_EXPOSURE)   +
            (crit_score    * self.W_CRITICALITY) +
            (temporal_score * self.W_TEMPORAL),
            2
        )

        # ── Tier assignment and SLA ───────────────────────────────────────
        if self.risk_score >= 80:
            self.risk_tier       = "critical"
            self.patch_sla_hours = 4          # Patch within 4 hours
            self.auto_approve    = False       # ALWAYS require human approval
        elif self.risk_score >= 60:
            self.risk_tier       = "high"
            self.patch_sla_hours = 24          # Patch within 24 hours
            self.auto_approve    = False       # Require human approval
        elif self.risk_score >= 40:
            self.risk_tier       = "medium"
            self.patch_sla_hours = 72          # Patch within 72 hours
            self.auto_approve    = True        # Safe for automated patching
        else:
            self.risk_tier       = "low"
            self.patch_sla_hours = 336         # Patch within 14 days
            self.auto_approve    = True        # Safe for automated patching

        return self

    def to_dict(self) -> dict:
        return {
            "cve_id":            self.cve_id,
            "cvss_base":         self.cvss_base,
            "exploit_available": self.exploit_available,
            "affected_hosts":    self.affected_hosts,
            "total_hosts":       self.total_hosts,
            "business_tier":     self.business_tier,
            "days_since_pub":    self.days_since_pub,
            "risk_score":        self.risk_score,
            "risk_tier":         self.risk_tier,
            "patch_sla_hours":   self.patch_sla_hours,
            "auto_approve":      self.auto_approve,
            "dimensions": {
                "cvss_normalized":    round((self.cvss_base/10)*100, 1),
                "exploit_score":      100 if self.exploit_available else 20,
                "exposure_pct":       round((self.affected_hosts/max(self.total_hosts,1))*100, 1),
                "criticality_tier":   self.business_tier,
                "temporal_days":      self.days_since_pub,
            }
        }

    def __str__(self):
        return (
            f"CVE: {self.cve_id}\n"
            f"  Risk Score   : {self.risk_score}/100\n"
            f"  Risk Tier    : {self.risk_tier}\n"
            f"  SLA          : {self.patch_sla_hours}h\n"
            f"  Auto-Approve : {self.auto_approve}\n"
            f"  CVSS Base    : {self.cvss_base}\n"
            f"  Exploited    : {self.exploit_available}\n"
            f"  Affected     : {self.affected_hosts}/{self.total_hosts} hosts\n"
            f"  Age          : {self.days_since_pub} days"
        )


def main():
    parser = argparse.ArgumentParser(
        description="Five-dimension CVE risk scorer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 cve_risk_scorer.py --cve CVE-2024-1234 --cvss 9.8 \\
      --exploit --affected-hosts 847 --total-hosts 4500 --tier standard

  python3 cve_risk_scorer.py --cve CVE-2024-2345 --cvss 6.5 \\
      --affected-hosts 3200 --total-hosts 4500 --days 45 --tier high
        """
    )
    parser.add_argument("--cve",            required=True)
    parser.add_argument("--cvss",           type=float, default=0.0)
    parser.add_argument("--exploit",        action="store_true",
                        help="CVE is in CISA KEV or has public exploit")
    parser.add_argument("--affected-hosts", type=int, required=True)
    parser.add_argument("--total-hosts",    type=int, default=4500)
    parser.add_argument("--tier",           default="standard",
                        choices=["critical","high","standard","low"])
    parser.add_argument("--days",           type=int, default=0,
                        help="Days since CVE publication")
    parser.add_argument("--json",           action="store_true")
    args = parser.parse_args()

    score = CVERiskScore(
        cve_id=args.cve,
        cvss_base=args.cvss,
        exploit_available=args.exploit,
        affected_hosts=args.affected_hosts,
        total_hosts=args.total_hosts,
        business_tier=args.tier,
        days_since_pub=args.days,
    ).compute()

    if args.json:
        print(json.dumps(score.to_dict(), indent=2))
    else:
        print(str(score))


if __name__ == "__main__":
    main()
