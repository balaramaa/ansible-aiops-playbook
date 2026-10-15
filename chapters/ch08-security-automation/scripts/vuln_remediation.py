#!/usr/bin/env python3
"""
vuln_remediation.py — Chapter 8, Listing 8-8
Automated vulnerability remediation pipeline.
Integrates Tenable/Qualys findings with Ansible remediation.

Author : Balaramakrishna Alti
GitHub : https://github.com/balaramaa/ansible-aiops-playbook

Usage:
    # View remediation plan (mock mode)
    python3 vuln_remediation.py --mock --plan

    # Execute auto-remediable vulnerabilities
    python3 vuln_remediation.py --execute --group lab

    # Tenable.io integration
    export TENABLE_ACCESS_KEY="..."
    export TENABLE_SECRET_KEY="..."
    python3 vuln_remediation.py --plan --min-severity 3
"""

import argparse, json, logging, os, subprocess
from dataclasses import dataclass
import requests

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)


@dataclass
class Vulnerability:
    plugin_id:   str
    severity:    int      # 0=Info 1=Low 2=Medium 3=High 4=Critical
    cvss_score:  float
    cve:         str
    description: str
    solution:    str
    host:        str
    port:        int = 0

    SEVERITY_NAMES = {0:"info", 1:"low", 2:"medium", 3:"high", 4:"critical"}

    @property
    def severity_name(self) -> str:
        return self.SEVERITY_NAMES.get(self.severity, "unknown")

    @property
    def auto_remediable(self) -> bool:
        """Medium severity and below are safe for automated remediation."""
        return self.severity <= 2


class TenableClient:
    """Tenable.io API client. Set TENABLE_MOCK=true for lab mode."""

    def __init__(self, mock: bool = False):
        self.access_key = os.environ.get("TENABLE_ACCESS_KEY", "")
        self.secret_key = os.environ.get("TENABLE_SECRET_KEY", "")
        self.base_url   = "https://cloud.tenable.com"
        self.mock       = (mock or
                          os.environ.get("TENABLE_MOCK","false").lower() == "true")
        self.headers    = {
            "X-ApiKeys": f"accessKey={self.access_key};secretKey={self.secret_key}",
            "Content-Type": "application/json",
        }

    def get_vulnerabilities(self, min_severity: int = 2) -> list:
        if self.mock:
            return self._mock_vulns()

        response = requests.post(
            f"{self.base_url}/workbenches/vulnerabilities",
            headers=self.headers,
            json={"filters": [
                {"filter": "severity", "quality": "gte", "value": str(min_severity)}
            ]},
            timeout=30
        )
        response.raise_for_status()
        vulns = []
        for v in response.json().get("vulnerabilities", []):
            vulns.append(Vulnerability(
                plugin_id   = str(v.get("plugin", {}).get("id", "")),
                severity    = v.get("severity", {}).get("id", 0),
                cvss_score  = float(v.get("severity", {}).get("cvss3_base_score", 0.0) or 0),
                cve         = (v.get("plugin", {}).get("cve") or [None])[0] or "",
                description = (v.get("plugin", {}).get("description") or "")[:200],
                solution    = v.get("plugin", {}).get("solution") or "",
                host        = v.get("asset", {}).get("hostname", ""),
                port        = v.get("port", {}).get("port", 0),
            ))
        log.info(f"Retrieved {len(vulns)} vulnerabilities from Tenable")
        return vulns

    def _mock_vulns(self) -> list:
        log.info("Using mock vulnerability data")
        return [
            Vulnerability("19506", 4, 9.8, "CVE-2024-1234",
                "OpenSSL memory corruption — remote code execution",
                "dnf update openssl openssl-libs",
                "node01", 443),
            Vulnerability("45411", 3, 7.5, "CVE-2024-2345",
                "curl command injection vulnerability",
                "dnf update curl libcurl",
                "node02", 80),
            Vulnerability("20007", 2, 5.4, "CVE-2024-3456",
                "Python requests library SSRF vulnerability",
                "pip3 install --upgrade requests",
                "node03", 0),
            Vulnerability("67890", 2, 4.3, "CVE-2024-4567",
                "bind-utils information disclosure",
                "dnf update bind-utils",
                "node01", 53),
        ]


def build_remediation_plan(vulns: list) -> dict:
    """Build prioritized remediation plan."""
    plan = {
        "total":          len(vulns),
        "auto_remediate": [],
        "manual_review":  [],
        "by_host":        {},
    }

    for v in sorted(vulns, key=lambda x: (-x.severity, -x.cvss_score)):
        entry = {
            "host":        v.host,
            "plugin_id":   v.plugin_id,
            "cve":         v.cve,
            "severity":    v.severity_name,
            "cvss":        v.cvss_score,
            "description": v.description[:100],
            "solution":    v.solution,
        }
        bucket = "auto_remediate" if v.auto_remediable else "manual_review"
        plan[bucket].append(entry)

        if v.host not in plan["by_host"]:
            plan["by_host"][v.host] = {"critical":0,"high":0,"medium":0,"low":0}
        plan["by_host"][v.host][v.severity_name] = (
            plan["by_host"][v.host].get(v.severity_name, 0) + 1
        )

    return plan


def execute_remediation(vuln: dict, host_group: str, dry_run: bool = True) -> dict:
    """Execute remediation via Ansible ad-hoc or playbook."""
    solution = vuln.get("solution", "")

    # Parse solution into Ansible-executable command
    if "dnf update" in solution or "dnf upgrade" in solution:
        packages = solution.replace("dnf update","").replace("dnf upgrade","").strip()
        cmd = [
            "ansible", vuln["host"],
            "-i", "inventory/",
            "-m", "ansible.builtin.dnf",
            "-a", f"name={packages} state=latest",
            "--become"
        ]
        if dry_run:
            cmd.extend(["--check", "--diff"])
    else:
        return {"status": "skipped",
                "reason": f"Solution requires manual review: {solution[:60]}"}

    result = subprocess.run(cmd, capture_output=True, text=True)
    return {
        "host":    vuln["host"],
        "cve":     vuln.get("cve"),
        "status":  "success" if result.returncode == 0 else "failed",
        "dry_run": dry_run,
        "solution": solution,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Vulnerability remediation pipeline"
    )
    parser.add_argument("--mock",        action="store_true")
    parser.add_argument("--plan",        action="store_true",
                        help="Show remediation plan")
    parser.add_argument("--execute",     action="store_true",
                        help="Execute auto-remediable vulnerabilities")
    parser.add_argument("--group",       default="all")
    parser.add_argument("--min-severity",type=int, default=2)
    args = parser.parse_args()

    client = TenableClient(mock=args.mock)
    vulns  = client.get_vulnerabilities(args.min_severity)
    plan   = build_remediation_plan(vulns)

    print(f"\nVulnerability Remediation Plan")
    print(f"{'='*55}")
    print(f"Total vulnerabilities : {plan['total']}")
    print(f"Auto-remediable       : {len(plan['auto_remediate'])}")
    print(f"Manual review required: {len(plan['manual_review'])}")

    print(f"\nBy host:")
    for host, counts in sorted(plan["by_host"].items()):
        print(f"  {host}: {counts}")

    if plan["manual_review"]:
        print(f"\nManual Review Required:")
        for v in plan["manual_review"]:
            print(f"  [{v['severity'].upper()}] {v['host']} — {v['cve']}: {v['description'][:50]}")
            print(f"    Fix: {v['solution']}")

    if args.execute:
        print(f"\nExecuting auto-remediable fixes...")
        for v in plan["auto_remediate"]:
            result = execute_remediation(v, args.group, dry_run=False)
            icon   = "✔" if result["status"] == "success" else "✗"
            print(f"  {icon} {v['host']} / {v['cve']}: {result['status']}")
    else:
        print(f"\n[DRY RUN] Use --execute to apply auto-remediable fixes")


if __name__ == "__main__":
    main()
