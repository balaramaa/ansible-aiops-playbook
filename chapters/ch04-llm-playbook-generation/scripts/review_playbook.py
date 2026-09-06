#!/usr/bin/env python3
"""
review_playbook.py — Chapter 4, Listing 4-5
AI-powered Ansible playbook security and quality reviewer.

Author : Balaramakrishna Alti
GitHub : https://github.com/balaramaa/ansible-aiops-playbook

Usage:
    python3 review_playbook.py --playbook roles/linux_baseline/tasks/main.yml
    python3 review_playbook.py --playbook site.yml --fail-on critical
    python3 review_playbook.py --playbook tasks.yml --json > report.json

Exit codes:
    0 — No issues at or above --fail-on severity
    1 — Issues found at or above --fail-on severity
    2 — Script error (file not found, API error, etc.)
"""

import argparse, json, sys, logging
from pathlib import Path
from llm_provider import get_provider

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

REVIEW_SYSTEM_PROMPT = """
You are a senior Ansible security engineer reviewing playbooks for production readiness.
Analyze the provided Ansible YAML and return a structured JSON report.

Return ONLY this JSON structure — no prose, no markdown fences:

{
  "summary": "One-sentence overall assessment",
  "score": <integer 0-100>,
  "issues": [
    {
      "severity": "critical|high|medium|low|info",
      "category": "security|idempotency|performance|style|best-practice",
      "line": <integer line number or null>,
      "description": "What is wrong",
      "remediation": "Specific fix"
    }
  ],
  "strengths": ["What the playbook does well"],
  "approved_for_production": <true|false>
}

Check for these issues:

SECURITY (critical/high):
- ansible.builtin.shell or command instead of appropriate module
- no_log: true missing on tasks handling passwords, keys, or tokens
- File permissions more permissive than necessary (e.g., mode 0777)
- PermitRootLogin yes or PasswordAuthentication yes in SSH configs
- Unencrypted sensitive variables (passwords in plaintext)
- Downloading and executing scripts without checksum verification

IDEMPOTENCY (high/medium):
- Operations that change state on every run regardless of current state
- Missing creates: or removes: on command/shell tasks
- Appending to files without idempotency check

BEST PRACTICE (medium/low):
- Missing name: on any task
- Non-fully-qualified module names (e.g., 'service' instead of 'ansible.builtin.service')
- Missing tags on tasks
- Missing changed_when: on command/shell tasks
- Missing failed_when: where exit codes may be ambiguous
- No handlers for service restarts (using service module in task instead)
- Missing ansible.builtin.assert for prerequisite validation
"""

SEVERITY_RANK = ["critical", "high", "medium", "low", "info"]


def review_playbook(playbook_path: str) -> dict:
    """Review an Ansible playbook file and return a structured report."""
    path = Path(playbook_path)
    if not path.exists():
        log.error(f"File not found: {playbook_path}")
        sys.exit(2)

    content = path.read_text()
    lines   = content.splitlines()
    provider = get_provider()

    log.info(f"Reviewing: {playbook_path} ({len(lines)} lines)")

    user_prompt = f"""Review this Ansible playbook file:

File: {playbook_path}
Lines: {len(lines)}

Content:
{content}

Provide a thorough security and quality review."""

    response = provider.generate(
        REVIEW_SYSTEM_PROMPT, user_prompt,
        temperature=0.0, max_tokens=3000
    )

    # Parse JSON — strip fences if present
    raw = response.content.strip()
    if raw.startswith("```"):
        raw = "\n".join(raw.splitlines()[1:])
    if raw.endswith("```"):
        raw = "\n".join(raw.splitlines()[:-1])

    try:
        report = json.loads(raw.strip())
    except json.JSONDecodeError as e:
        log.error(f"LLM returned invalid JSON: {e}")
        log.debug(f"Raw response: {raw[:500]}")
        report = {
            "summary": "Review failed — LLM returned invalid JSON",
            "score": 0,
            "issues": [],
            "strengths": [],
            "approved_for_production": False,
            "error": str(e)
        }

    report["reviewed_file"] = str(playbook_path)
    report["provider"] = response.provider
    report["model"]    = response.model
    report["elapsed"]  = response.elapsed_seconds
    return report


def print_report(report: dict) -> None:
    """Print a human-readable review report to stdout."""
    score    = report.get("score", 0)
    approved = report.get("approved_for_production", False)
    issues   = report.get("issues", [])

    # Colour codes
    GREEN = "\033[0;32m"; RED = "\033[0;31m"
    YELLOW = "\033[1;33m"; BOLD = "\033[1m"; NC = "\033[0m"

    sev_colours = {
        "critical": RED, "high": RED,
        "medium": YELLOW, "low": YELLOW, "info": NC
    }

    print(f"\n{BOLD}{'='*65}{NC}")
    print(f"{BOLD}ANSIBLE PLAYBOOK REVIEW REPORT{NC}")
    print(f"  File    : {report['reviewed_file']}")
    print(f"  Model   : {report['model']}")
    print(f"  Score   : {score}/100")
    status_str = f"{GREEN}✔ APPROVED{NC}" if approved else f"{RED}✗ NOT APPROVED{NC}"
    print(f"  Status  : {status_str}")
    print(f"{BOLD}{'='*65}{NC}")
    print(f"\nSummary: {report.get('summary','N/A')}")

    if issues:
        sorted_issues = sorted(
            issues,
            key=lambda x: SEVERITY_RANK.index(x.get("severity","info"))
        )
        print(f"\nIssues ({len(issues)}):")
        for issue in sorted_issues:
            sev   = issue.get("severity","info")
            col   = sev_colours.get(sev, NC)
            line  = f" (line {issue['line']})" if issue.get("line") else ""
            print(f"  {col}[{sev.upper()}]{NC}{line} {issue.get('description','')}")
            print(f"    → Fix: {issue.get('remediation','')}")
    else:
        print(f"\n{GREEN}No issues found.{NC}")

    strengths = report.get("strengths", [])
    if strengths:
        print("\nStrengths:")
        for s in strengths:
            print(f"  {GREEN}+{NC} {s}")


def main():
    parser = argparse.ArgumentParser(
        description="AI-powered Ansible playbook reviewer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 review_playbook.py --playbook roles/linux_baseline/tasks/main.yml
  python3 review_playbook.py --playbook site.yml --fail-on high
  python3 review_playbook.py --playbook tasks.yml --json | jq .score
        """
    )
    parser.add_argument("--playbook", required=True, help="Path to playbook or task file")
    parser.add_argument("--fail-on",
                        choices=SEVERITY_RANK[:-1],
                        help="Exit 1 if issues at this severity or higher are found")
    parser.add_argument("--json", action="store_true",
                        help="Output raw JSON report")
    args = parser.parse_args()

    report = review_playbook(args.playbook)

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print_report(report)

    # Exit non-zero if fail-on threshold is met
    if args.fail_on:
        threshold = SEVERITY_RANK.index(args.fail_on)
        for issue in report.get("issues", []):
            issue_rank = SEVERITY_RANK.index(issue.get("severity","info"))
            if issue_rank <= threshold:
                log.error(f"Failing CI: found {issue['severity']} severity issue")
                sys.exit(1)


if __name__ == "__main__":
    main()
