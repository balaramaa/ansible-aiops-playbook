#!/usr/bin/env python3
"""
migration_assessor.py — Chapter 12, Listing 12-2
AI-powered migration readiness assessment from discovery data.

Author : Balaramakrishna Alti
GitHub : https://github.com/balaramaa/ansible-aiops-playbook

Usage:
    # Assess all servers from a discovery run
    python3 migration_assessor.py \
        --discovery-dir /tmp/migration_discovery/rms-2024-10-01/ \
        --output /tmp/assessment_results.json

    # Assess with custom standards
    python3 migration_assessor.py \
        --discovery-dir /tmp/migration_discovery/rms-2024-10-01/ \
        --standards chapters/ch12-migration/scripts/migration_standards.json

    # Mock mode for lab (no LLM required)
    python3 migration_assessor.py \
        --discovery-dir /tmp/migration_discovery/lab-2024-10-01/ \
        --mock
"""

import argparse, json, logging, sys
from dataclasses import dataclass, asdict
from pathlib import Path

sys.path.insert(0, "../../ch04-llm-playbook-generation/scripts")
from llm_provider import get_provider

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

ASSESSOR_PROMPT = """
You are an enterprise Linux infrastructure migration expert.
Assess server migration readiness and return ONLY this JSON:

{
  "readiness_score": <integer 0-100>,
  "category": "ready|needs_remediation|manual_review",
  "blockers": [
    {
      "issue": "Clear description of the blocker",
      "severity": "critical|high|medium",
      "remediation": "Specific fix command or procedure",
      "auto_fixable": true|false,
      "estimated_fix_hours": <float>
    }
  ],
  "warnings": ["Non-blocking warning 1", "Warning 2"],
  "estimated_migration_hours": <float>,
  "recommended_batch": "early|mid|late",
  "summary": "One sentence readiness assessment"
}

Scoring guide:
  90-100 → ready:             Proceed immediately
  60-89  → needs_remediation: Specific issues to fix first
  0-59   → manual_review:     Complex case, needs human assessment

Key rules:
  - RHEL/Rocky 8 or 9: baseline score 70
  - RHEL/Rocky 7 (needs upgrade): score 50, high blocker
  - RHEL 6 or unsupported OS: score 20, critical blocker
  - Already Ansible-managed: +20 bonus
  - SELinux enforcing: +10 bonus
  - SELinux disabled: -20, high blocker
  - Has node_exporter: +5 bonus
  - Missing Ansible service account: -15, high blocker
  - SSH key count > 50: -5, medium blocker (audit required)
  - Legacy CM agents (puppet/chef/salt): medium blocker
  - recommended_batch: early (score>=90), mid (75-89), late (<75)
"""

DEFAULT_STANDARDS = {
    "target_os":           ["RedHat", "Rocky"],
    "target_os_version":   "9",
    "min_os_major":        8,
    "required_selinux":    "enforcing",
    "max_ssh_keys":        50,
    "required_packages":   ["chrony", "audit"],
    "forbidden_packages":  ["telnet", "rsh"],
}


@dataclass
class ReadinessReport:
    hostname:                  str
    readiness_score:           int
    category:                  str
    blockers:                  list
    warnings:                  list
    estimated_migration_hours: float
    recommended_batch:         str
    summary:                   str

    def is_ready(self) -> bool:
        return self.category == "ready"

    def has_critical_blockers(self) -> bool:
        return any(b.get("severity") == "critical" for b in self.blockers)

    def auto_fixable_blockers(self) -> list:
        return [b for b in self.blockers if b.get("auto_fixable")]


def assess_server(discovery: dict,
                  standards: dict = None,
                  mock: bool = False) -> ReadinessReport:
    """Assess a single server's migration readiness using AI analysis."""
    std      = standards or DEFAULT_STANDARDS
    hostname = discovery.get("host_profile", {}).get("hostname", "unknown")

    if mock:
        return _mock_assessment(hostname, discovery)

    provider = get_provider()
    prompt   = f"""Assess migration readiness for this server:

Discovery data:
{json.dumps(discovery, indent=2)}

Migration target standards:
{json.dumps(std, indent=2)}

Provide detailed readiness assessment with specific blockers and fixes."""

    log.info(f"Assessing: {hostname}")
    response = provider.generate(
        ASSESSOR_PROMPT, prompt,
        temperature=0.0, max_tokens=1024
    )
    raw = response.content.strip()
    if raw.startswith("```"): raw = raw.split("\n", 1)[1]
    if raw.endswith("```"):   raw = raw.rsplit("\n", 1)[0]

    data = json.loads(raw.strip())
    return ReadinessReport(
        hostname=hostname,
        readiness_score=data.get("readiness_score", 50),
        category=data.get("category", "manual_review"),
        blockers=data.get("blockers", []),
        warnings=data.get("warnings", []),
        estimated_migration_hours=float(data.get("estimated_migration_hours", 4.0)),
        recommended_batch=data.get("recommended_batch", "late"),
        summary=data.get("summary", ""),
    )


def _mock_assessment(hostname: str, discovery: dict) -> ReadinessReport:
    """Generate a realistic mock assessment for lab exercises."""
    hp    = discovery.get("host_profile", {})
    os_major = int(hp.get("os_major", 0))
    selinux  = hp.get("selinux_mode", "disabled")
    managed  = discovery.get("already_managed", False)

    blockers = []
    score    = 60

    if os_major >= 9:
        score += 20
    elif os_major == 8:
        score += 10
    elif os_major == 7:
        score -= 10
        blockers.append({
            "issue": "RHEL 7 requires in-place upgrade to RHEL 9 before migration",
            "severity": "high",
            "remediation": "Run rhel_upgrade.yml playbook first",
            "auto_fixable": True,
            "estimated_fix_hours": 2.0,
        })

    if selinux == "enforcing":
        score += 10
    elif selinux in ("permissive", "disabled"):
        blockers.append({
            "issue": f"SELinux is {selinux} — must be enforcing",
            "severity": "high",
            "remediation": "setenforce 1 && sed -i 's/SELINUX=.*/SELINUX=enforcing/' /etc/selinux/config",
            "auto_fixable": True,
            "estimated_fix_hours": 0.5,
        })

    if managed:
        score += 15

    ssh_keys = int(discovery.get("ssh_keys_total", 0))
    if ssh_keys > 50:
        blockers.append({
            "issue": f"High SSH authorized key count ({ssh_keys}) — audit required",
            "severity": "medium",
            "remediation": "Audit and remove unauthorized SSH keys",
            "auto_fixable": False,
            "estimated_fix_hours": 2.0,
        })

    score    = max(0, min(100, score))
    category = ("ready" if score >= 90
                else "needs_remediation" if score >= 60
                else "manual_review")
    batch    = ("early" if score >= 90
                else "mid" if score >= 75
                else "late")

    return ReadinessReport(
        hostname=hostname,
        readiness_score=score,
        category=category,
        blockers=blockers,
        warnings=[f"Mock assessment for lab exercise — {hostname}"],
        estimated_migration_hours=max(1.0, len(blockers) * 1.5 + 1.0),
        recommended_batch=batch,
        summary=f"{'Ready' if not blockers else 'Needs remediation'}: score {score}/100",
    )


def assess_fleet(discovery_dir: str,
                 standards: dict = None,
                 output_file: str = None,
                 mock: bool = False) -> list:
    """Assess all servers from a discovery run."""
    files   = sorted(Path(discovery_dir).glob("*.json"))
    files   = [f for f in files if f.name != "SUMMARY.json"]
    log.info(f"Assessing {len(files)} servers from {discovery_dir}")

    reports = []
    for f in files:
        discovery = json.loads(f.read_text())
        report    = assess_server(discovery, standards, mock)
        reports.append(report)
        log.info(f"  {report.hostname}: {report.category} ({report.readiness_score}/100)")

    if output_file:
        Path(output_file).write_text(
            json.dumps([asdict(r) for r in reports], indent=2)
        )
        log.info(f"Assessment saved: {output_file}")

    return reports


def print_summary(reports: list) -> None:
    ready     = [r for r in reports if r.category == "ready"]
    remediate = [r for r in reports if r.category == "needs_remediation"]
    manual    = [r for r in reports if r.category == "manual_review"]
    total_hrs = sum(r.estimated_migration_hours for r in reports)

    print(f"\nMigration Readiness Assessment")
    print(f"{'='*55}")
    print(f"Total servers assessed  : {len(reports)}")
    print(f"Ready to migrate        : {len(ready)} "
          f"({len(ready)/max(len(reports),1)*100:.0f}%)")
    print(f"Needs remediation       : {len(remediate)}")
    print(f"Manual review required  : {len(manual)}")
    print(f"Estimated effort (total): {total_hrs:.0f} hours")
    avg_score = sum(r.readiness_score for r in reports) / max(len(reports), 1)
    print(f"Average readiness score : {avg_score:.1f}/100")

    if manual:
        print(f"\nManual Review Required ({len(manual)} servers):")
        for r in manual:
            print(f"  [{r.readiness_score:3d}] {r.hostname}: {r.summary}")
            for b in r.blockers:
                fixable = "AUTO" if b.get("auto_fixable") else "MANUAL"
                print(f"        [{b['severity'].upper()}/{fixable}] {b['issue']}")

    if remediate:
        print(f"\nNeeds Remediation ({len(remediate)} servers):")
        for r in remediate:
            critical = [b for b in r.blockers if b["severity"] == "critical"]
            high     = [b for b in r.blockers if b["severity"] == "high"]
            print(f"  [{r.readiness_score:3d}] {r.hostname}: "
                  f"{len(critical)} critical, {len(high)} high blockers")


def main():
    parser = argparse.ArgumentParser(
        description="AI-powered migration readiness assessor"
    )
    parser.add_argument("--discovery-dir", required=True,
                        help="Directory with discovery JSON files")
    parser.add_argument("--output",        help="Save assessment results to JSON file")
    parser.add_argument("--standards",     help="Custom migration standards JSON file")
    parser.add_argument("--mock",          action="store_true",
                        help="Mock mode — no LLM required (lab exercise)")
    parser.add_argument("--json",          action="store_true",
                        help="Output assessment as JSON")
    args = parser.parse_args()

    standards = None
    if args.standards:
        standards = json.loads(Path(args.standards).read_text())

    reports = assess_fleet(
        args.discovery_dir,
        standards=standards,
        output_file=args.output,
        mock=args.mock,
    )

    if args.json:
        from dataclasses import asdict
        print(json.dumps([asdict(r) for r in reports], indent=2))
    else:
        print_summary(reports)


if __name__ == "__main__":
    main()
