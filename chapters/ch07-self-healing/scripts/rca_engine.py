#!/usr/bin/env python3
"""
rca_engine.py — Chapter 7, Listing 7-4
AI-powered root cause analysis engine for infrastructure incidents.

Author : Balaramakrishna Alti
GitHub : https://github.com/balaramaa/ansible-aiops-playbook

Usage:
    python3 rca_engine.py --host node01 --alert HighMemoryUsage
    python3 rca_engine.py --host node01 --alert ServiceDown \
        --context "nginx was recently updated"
"""

import argparse, json, logging, subprocess, sys
from datetime import datetime, timezone

sys.path.insert(0, "../../ch04-llm-playbook-generation/scripts")
from llm_provider import get_provider

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

RCA_SYSTEM_PROMPT = """
You are an expert Linux systems engineer performing root cause analysis.
Analyze the provided incident data and return ONLY this JSON structure:

{
  "probable_root_cause": "Most likely single root cause in one sentence",
  "confidence": "high|medium|low",
  "evidence": ["Key evidence 1", "Key evidence 2", "Key evidence 3"],
  "contributing_factors": ["Factor 1", "Factor 2"],
  "immediate_action": "What to do right now to resolve the incident",
  "permanent_fix": "Long-term fix to prevent recurrence",
  "safe_to_auto_remediate": true|false,
  "escalate_reason": "Why human review is needed (if safe_to_auto_remediate is false)"
}

Common Linux failure patterns to consider:
- Memory leaks in Java/Python processes (check OOM killer in dmesg/journal)
- Disk exhaustion from log files, core dumps, or temp files
- Network saturation from backup, replication, or batch jobs
- Service crashes due to missing config, permissions, or dependencies
- CPU spikes from cron jobs, runaway loops, or kernel bugs
- Compliance drift from unauthorized manual changes (check auditd)
- Certificate expiry causing authentication failures
"""


def collect_diagnostics(hostname: str,
                         alert_name: str,
                         lookback_minutes: int = 30) -> dict:
    """Collect live diagnostics from host via Ansible ad-hoc commands."""
    log.info(f"Collecting diagnostics from {hostname}")
    diag = {}

    def run_ansible(cmd_str: str) -> str:
        cmd = [
            "ansible", hostname, "-i", "inventory/",
            "-m", "ansible.builtin.shell",
            "-a", cmd_str, "--become"
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            # Extract stdout from ansible output
            for line in result.stdout.splitlines():
                if "| CHANGED | rc=0 >>" in line or "| SUCCESS | rc=0 >>" in line:
                    idx = result.stdout.find(line) + len(line) + 1
                    return result.stdout[idx:idx+2000].strip()
        return ""

    diag["journal_errors"]    = run_ansible(
        f"journalctl --since='{lookback_minutes} minutes ago' -p err --no-pager -n 40"
    )
    diag["top_memory_procs"]  = run_ansible("ps aux --sort=-%mem --no-headers | head -8")
    diag["top_cpu_procs"]     = run_ansible("ps aux --sort=-%cpu --no-headers | head -8")
    diag["disk_usage"]        = run_ansible("df -h")
    diag["failed_services"]   = run_ansible("systemctl --failed --no-legend")
    diag["recent_audit"]      = run_ansible("ausearch --start recent -i 2>/dev/null | tail -15")
    diag["dmesg_errors"]      = run_ansible("dmesg --level=err,crit --since '30 minutes ago' 2>/dev/null | tail -20")
    diag["hostname"]          = hostname
    diag["alert_name"]        = alert_name
    diag["collected_at"]      = datetime.now(timezone.utc).isoformat()
    return diag


def analyze(hostname: str,
            alert_name: str,
            additional_context: str = "",
            mock: bool = False) -> dict:
    """
    Run AI-powered RCA on a host incident.

    Args:
        hostname:           Target hostname
        alert_name:         Alert or event name
        additional_context: Any additional information about the incident
        mock:               If True, use mock diagnostics (no Ansible required)

    Returns:
        RCA result dict with root cause, evidence, and remediation guidance
    """
    if mock:
        diagnostics = {
            "hostname":        hostname,
            "alert_name":      alert_name,
            "collected_at":    datetime.now(timezone.utc).isoformat(),
            "journal_errors":  "Nov 01 03:14:22 node01 kernel: Out of memory: Kill process 12345 (java) score 892",
            "top_memory_procs":"USER       PID %CPU %MEM   RSS COMMAND\nroot     12345  2.1 94.3 7823456 java -jar app.jar",
            "top_cpu_procs":   "USER       PID %CPU %MEM COMMAND\nroot     12345  2.1 94.3 java",
            "disk_usage":      "Filesystem      Size  Used Avail Use%\n/dev/sda1        50G   12G   38G  24%",
            "failed_services": "",
            "recent_audit":    "",
            "dmesg_errors":    "kernel: Out of memory: Kill process 12345 (java)",
        }
    else:
        diagnostics = collect_diagnostics(hostname, alert_name)

    provider = get_provider()

    prompt = f"""Perform root cause analysis for this infrastructure incident:

Host:    {hostname}
Alert:   {alert_name}
Time:    {diagnostics['collected_at']}
{f'Context: {additional_context}' if additional_context else ''}

Journal errors (last 30 min):
{diagnostics.get('journal_errors', 'N/A')[:1500]}

Top memory consumers:
{diagnostics.get('top_memory_procs', 'N/A')}

Top CPU consumers:
{diagnostics.get('top_cpu_procs', 'N/A')}

Disk usage:
{diagnostics.get('disk_usage', 'N/A')}

Failed services:
{diagnostics.get('failed_services', 'none')}

dmesg errors:
{diagnostics.get('dmesg_errors', 'none')}

Identify the probable root cause and provide remediation guidance."""

    log.info(f"Running AI RCA using {get_provider().__class__.__name__}")
    response = provider.generate(RCA_SYSTEM_PROMPT, prompt,
                                  temperature=0.0, max_tokens=1024)

    raw = response.content.strip()
    if raw.startswith("```"): raw = raw.split("\n", 1)[1]
    if raw.endswith("```"):   raw = raw.rsplit("\n", 1)[0]

    rca = json.loads(raw.strip())
    rca["hostname"]          = hostname
    rca["alert_name"]        = alert_name
    rca["analyzed_by"]       = response.model
    rca["analysis_time"]     = diagnostics["collected_at"]
    rca["elapsed_seconds"]   = response.elapsed_seconds
    return rca


def main():
    parser = argparse.ArgumentParser(description="AI-powered RCA engine")
    parser.add_argument("--host",    required=True)
    parser.add_argument("--alert",   required=True)
    parser.add_argument("--context", default="")
    parser.add_argument("--mock",    action="store_true",
                        help="Use mock diagnostics (no live Ansible required)")
    args = parser.parse_args()

    rca = analyze(args.host, args.alert, args.context, args.mock)

    print(f"\n{'='*60}")
    print(f"RCA REPORT — {args.host} / {args.alert}")
    print(f"{'='*60}")
    print(f"Root Cause  : {rca['probable_root_cause']}")
    print(f"Confidence  : {rca['confidence']}")
    print(f"Auto-Fix    : {rca['safe_to_auto_remediate']}")
    print(f"\nImmediate   : {rca['immediate_action']}")
    print(f"Permanent   : {rca['permanent_fix']}")
    print(f"\nEvidence:")
    for e in rca.get("evidence", []):
        print(f"  • {e}")

    if not rca["safe_to_auto_remediate"]:
        print(f"\n⚠  ESCALATE: {rca.get('escalate_reason','')}")

    print(f"\nAnalyzed by: {rca['analyzed_by']} in {rca['elapsed_seconds']}s")

    # Exit 1 if escalation needed — useful for pipeline integration
    if not rca["safe_to_auto_remediate"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
