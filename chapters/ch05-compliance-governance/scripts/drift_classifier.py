#!/usr/bin/env python3
"""
drift_classifier.py — Chapter 5, Listing 5-6
AI-powered compliance drift classification and risk scoring.

Author : Balaramakrishna Alti
GitHub : https://github.com/balaramaa/ansible-aiops-playbook

Usage:
    python3 drift_classifier.py --drift-report drift.json
    python3 drift_classifier.py --drift-report drift.json --context context.json
"""

import argparse, json, logging, sys
from pathlib import Path

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

# Import provider from Chapter 4
sys.path.insert(0, "../../ch04-llm-playbook-generation/scripts")
from llm_provider import get_provider

CLASSIFIER_SYSTEM_PROMPT = """
You are a Linux security compliance expert analyzing infrastructure drift.
Return ONLY this JSON structure — no prose, no markdown fences:

{
  "risk_score": <integer 1-100>,
  "risk_level": "critical|high|medium|low",
  "likely_cause": "Most probable reason for this drift pattern",
  "regulatory_impact": {
    "sox": true|false,
    "pci_dss": true|false,
    "nist_800_53": true|false
  },
  "remediation_priority": "immediate|scheduled|monitoring",
  "recommended_action": "Specific remediation recommendation",
  "auto_remediate": true|false,
  "auto_remediate_rationale": "Why auto-remediation is or is not safe here"
}

Risk scoring guide:
- 80-100 (critical): Active security risk, likely breach or regulatory violation
- 60-79  (high):     Significant compliance gap, remediate within 4 hours
- 40-59  (medium):   Compliance drift, remediate within 24 hours
- 1-39   (low):      Minor drift, remediate at next maintenance window

Set auto_remediate=true ONLY when:
1. Risk level is medium or low
2. Remediation restores configuration (not destructive)
3. No service disruption is expected from automated remediation
"""


def classify_drift(drift_report: dict,
                   server_context: dict = None) -> dict:
    """
    Classify compliance drift using AI and return risk assessment.

    Args:
        drift_report:   Output from compliance_baseline.detect_drift()
        server_context: Optional context dict with role, environment, criticality

    Returns:
        Classification dict with risk score, level, and remediation guidance
    """
    provider = get_provider()

    context_str = ""
    if server_context:
        context_str = f"""
Server context:
- Role:          {server_context.get('role', 'unknown')}
- Environment:   {server_context.get('environment', 'unknown')}
- Criticality:   {server_context.get('criticality', 'standard')}
- Applications:  {', '.join(server_context.get('applications', []))}
- Last compliant: {server_context.get('last_compliant', 'unknown')}
"""

    prompt = f"""Analyze this compliance drift report and classify the risk:

{json.dumps(drift_report, indent=2)}
{context_str}
Provide risk classification and remediation guidance."""

    log.info(f"Classifying drift for {drift_report.get('hostname')} "
             f"using {provider.__class__.__name__}")

    response = provider.generate(
        CLASSIFIER_SYSTEM_PROMPT, prompt,
        temperature=0.0, max_tokens=1024
    )

    raw = response.content.strip()
    if raw.startswith("```"): raw = raw.split("\n", 1)[1]
    if raw.endswith("```"):   raw = raw.rsplit("\n", 1)[0]

    classification = json.loads(raw.strip())
    classification["classified_by"] = response.model
    classification["hostname"]      = drift_report.get("hostname")
    classification["elapsed_s"]     = response.elapsed_seconds

    log.info(f"Classification: risk_level={classification['risk_level']} "
             f"score={classification['risk_score']} "
             f"auto_remediate={classification['auto_remediate']}")

    return classification


def main():
    parser = argparse.ArgumentParser(
        description="AI-powered compliance drift classifier"
    )
    parser.add_argument("--drift-report", required=True,
                        help="Path to drift report JSON from compliance_baseline.py")
    parser.add_argument("--context", help="Path to server context JSON file")
    args = parser.parse_args()

    drift_report = json.loads(Path(args.drift_report).read_text())
    server_context = None
    if args.context:
        server_context = json.loads(Path(args.context).read_text())

    classification = classify_drift(drift_report, server_context)
    print(json.dumps(classification, indent=2))

    # Exit 1 if critical or high — useful for pipeline integration
    if classification["risk_level"] in ("critical", "high"):
        log.error(f"HIGH/CRITICAL risk detected — manual review required")
        sys.exit(1)


if __name__ == "__main__":
    main()
