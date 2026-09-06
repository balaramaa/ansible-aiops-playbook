#!/usr/bin/env python3
"""
generate_evidence.py — Chapter 5, Listing 5-10
Generate regulatory evidence packages for SOX and PCI-DSS auditors.

Author : Balaramakrishna Alti
GitHub : https://github.com/balaramaa/ansible-aiops-playbook

Usage:
    python3 generate_evidence.py --framework sox
    python3 generate_evidence.py --framework pci_dss --days 90
    python3 generate_evidence.py --framework nist --output /tmp/evidence
"""

import argparse, csv, io, json, logging, zipfile
from datetime import datetime, timezone, timedelta
from pathlib import Path

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

REPORT_DIR   = Path("/var/log/compliance")
AUDIT_LOG    = REPORT_DIR / "remediation_audit.jsonl"
EVIDENCE_DIR = REPORT_DIR / "evidence_packages"

# CIS to NIST/SOX/PCI-DSS control mapping
CONTROL_MAPPING = [
    ("CIS 5.1.1", "SSH PermitRootLogin disabled",          "IA-2, AC-6",   "8.6.1",  "404"),
    ("CIS 5.1.7", "SSH MaxAuthTries ≤ 4",                  "AC-7",         "8.3.4",  "404"),
    ("CIS 5.1.10","SSH PermitEmptyPasswords disabled",      "IA-5",         "8.2.1",  "404"),
    ("CIS 5.1.20","SSH idle timeout configured",            "AC-12, SC-10", "8.6.3",  "404"),
    ("CIS 1.7",   "SELinux enforcing mode",                 "AC-3, SC-7",   "6.3.1",  "302"),
    ("CIS 4.1.x", "auditd enabled with CIS rules",         "AU-2, AU-12",  "10.2.x", "404"),
    ("CIS 1.4",   "Filesystem integrity checking (AIDE)",   "SI-7",         "11.3.1", "302"),
    ("CIS 2.2.x", "Unnecessary services removed",           "CM-7",         "2.2.1",  "302"),
    ("CIS 5.3.1", "Password maximum age ≤ 365 days",        "IA-5",         "8.3.9",  "404"),
    ("CIS 5.2.1", "Password complexity requirements",       "IA-5",         "8.3.6",  "404"),
]


def generate_evidence_package(audit_period_days: int = 90,
                               framework: str = "sox",
                               output_dir: str = None) -> Path:
    """Generate a compliance evidence package for auditors."""
    timestamp = datetime.now(timezone.utc)
    package_name = (
        f"compliance_evidence_{framework}_"
        f"{timestamp.strftime('%Y%m%d_%H%M%S')}.zip"
    )

    out_dir = Path(output_dir) if output_dir else EVIDENCE_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    package_path = out_dir / package_name

    log.info(f"Generating {framework.upper()} evidence package: {package_path}")

    with zipfile.ZipFile(package_path, "w", zipfile.ZIP_DEFLATED) as zf:

        # 00 — Executive Summary
        summary = {
            "package_type":    f"Compliance Evidence Package — {framework.upper()}",
            "generated_at":    timestamp.isoformat(),
            "audit_period":    f"Last {audit_period_days} days",
            "generated_by":    "Ansible AIOps Compliance Automation",
            "coverage":        "All servers managed by Ansible Automation Platform",
            "tool":            "Ansible 2.15+ with OpenSCAP SCAP Security Guide",
        }
        zf.writestr("00_executive_summary.json", json.dumps(summary, indent=2))

        # 01 — Remediation Audit Log
        if AUDIT_LOG.exists():
            cutoff = timestamp - timedelta(days=audit_period_days)
            relevant_lines = []
            for line in AUDIT_LOG.read_text().splitlines():
                try:
                    entry = json.loads(line)
                    entry_time = datetime.fromisoformat(entry.get("timestamp",""))
                    if entry_time >= cutoff:
                        relevant_lines.append(line)
                except: pass
            if relevant_lines:
                zf.writestr("01_remediation_audit_log.jsonl",
                            "\n".join(relevant_lines))
                log.info(f"Included {len(relevant_lines)} remediation records")

        # 02 — OpenSCAP HTML Reports
        reports = sorted(REPORT_DIR.glob("report-*.html"))
        cutoff_date = (timestamp - timedelta(days=audit_period_days)).strftime("%Y-%m-%d")
        for report in reports:
            if report.stem.split("-", 1)[1] >= cutoff_date:
                zf.write(report, f"02_scap_reports/{report.name}")
        log.info(f"Included {len(reports)} OpenSCAP reports")

        # 03 — Control Mapping CSV
        mapping_csv = _build_control_mapping_csv(framework)
        zf.writestr("03_control_mapping.csv", mapping_csv)

        # 04 — Attestation Statement
        attestation = _build_attestation(framework, timestamp, audit_period_days)
        zf.writestr("04_attestation.txt", attestation)

    log.info(f"✔ Evidence package generated: {package_path}")
    log.info(f"  Size: {package_path.stat().st_size:,} bytes")
    return package_path


def _build_control_mapping_csv(framework: str) -> str:
    """Build CSV mapping CIS controls to the target framework."""
    output = io.StringIO()
    framework_col = {
        "sox": "SOX Section",
        "pci_dss": "PCI-DSS Req.",
        "nist": "NIST 800-53",
    }.get(framework, "Framework Ref")

    writer = csv.writer(output)
    writer.writerow(["CIS Control", "Description", "NIST 800-53", "PCI-DSS", "SOX",
                     "Automated", "Verification Method"])
    for row in CONTROL_MAPPING:
        cis_id, desc, nist, pci, sox = row
        writer.writerow([cis_id, desc, nist, pci, sox,
                         "Yes — Ansible + OpenSCAP",
                         "OpenSCAP XCCDF scan + auditd log"])
    return output.getvalue()


def _build_attestation(framework: str,
                        timestamp: datetime,
                        days: int) -> str:
    return f"""
COMPLIANCE ATTESTATION — {framework.upper()}
{'='*55}

Generated:      {timestamp.isoformat()}
Audit Period:   Last {days} days
Organization:   [Your Organization Name]

STATEMENT OF COMPLIANCE
-----------------------
This evidence package was generated automatically by the
Ansible AIOps Compliance Automation system (The Ansible
AIOps Playbook, Apress/Springer Nature, 2026).

The following controls were continuously monitored during
the audit period:

  - CIS RHEL 9 Benchmark Level 1 (all managed servers)
  - CIS RHEL 9 Benchmark Level 2 (production servers)
  - NIST SP 800-53 Rev. 5 controls (mapped to CIS)
  {'- SOX Section 302/404 technical controls' if framework == 'sox' else ''}
  {'- PCI-DSS v4.0 Requirements 2, 6, 8, 10' if framework == 'pci_dss' else ''}

Monitoring Frequency:  Continuous (Event-Driven Ansible)
Scan Frequency:        Daily OpenSCAP scans per host
Remediation:           Automated (low/medium risk)
                       Manual approval (high/critical risk)

All remediation actions are logged with timestamps,
host identifiers, risk classifications, and outcomes
in file: 01_remediation_audit_log.jsonl

{'='*55}
This attestation was generated automatically.
Human review and sign-off required before submission to auditors.
"""


def main():
    parser = argparse.ArgumentParser(
        description="Generate regulatory compliance evidence packages"
    )
    parser.add_argument("--framework",
                        choices=["sox", "pci_dss", "nist"],
                        default="sox")
    parser.add_argument("--days", type=int, default=90,
                        help="Audit period in days (default: 90)")
    parser.add_argument("--output", help="Output directory")
    args = parser.parse_args()

    package = generate_evidence_package(
        audit_period_days=args.days,
        framework=args.framework,
        output_dir=args.output
    )
    print(f"\nEvidence package: {package}")
    print("Submit this ZIP to your compliance auditor.")


if __name__ == "__main__":
    main()
