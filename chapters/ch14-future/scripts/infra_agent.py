#!/usr/bin/env python3
"""
infra_agent.py — Chapter 14, Listing 14-1
Autonomous infrastructure investigation agent using ReAct pattern.

Author : Balaramakrishna Alti
GitHub : https://github.com/balaramaa/ansible-aiops-playbook

Usage:
    # Mock mode — no Prometheus/Loki/Ansible required
    python3 infra_agent.py \
        --goal "Investigate high memory usage on node01" \
        --mock

    # Live mode
    python3 infra_agent.py \
        --goal "Why was node03 paged at 3am?" \
        --prometheus http://prometheus:9090

    # Save investigation report
    python3 infra_agent.py \
        --goal "Investigate CPU spike on payments service" \
        --mock \
        --output /tmp/investigation_report.json
"""

import argparse, json, logging, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, "../../ch04-llm-playbook-generation/scripts")
from llm_provider import get_provider

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

AGENT_SYSTEM_PROMPT = """
You are an autonomous infrastructure investigation agent for enterprise Linux systems.
You have access to these tools to investigate infrastructure issues:

Tools available:
- query_prometheus(query, duration): Execute PromQL query for metrics
- search_logs(pattern, host, minutes): Search recent log entries
- run_ansible_adhoc(host, module, args): Run live diagnostic command
- check_audit_log(host, event_type): Query self-healing audit history
- get_recent_deployments(service, hours): Check recent CI/CD changes

Investigation process:
1. Analyze the goal and form an initial hypothesis
2. Choose the most relevant tool to gather evidence
3. Analyze the result and refine your hypothesis
4. Continue gathering evidence until you have high confidence
5. Produce a final structured report

For each step, return either:
  Tool call: {"tool": "<name>", "args": {<params>}, "reasoning": "<why this tool>"}
  Final report: {"type": "final_report", "findings": {
    "root_cause": "<what caused the issue>",
    "evidence": ["Evidence 1", "Evidence 2"],
    "timeline": "<when did it start>",
    "impact": "<what was affected>",
    "recommendation": "<immediate fix>",
    "prevention": "<how to prevent recurrence>",
    "confidence": "high|medium|low"
  }}

Guidelines:
- Start with metrics (Prometheus) to understand the scope
- Use logs to get context and error details
- Use Ansible ad-hoc for live state verification
- Check audit log to see if self-healing already acted
- Check deployments if timing correlates with a release
- Maximum 8 tool calls before producing final report
"""

TOOLS = {
    "query_prometheus": {
        "description": "Execute a PromQL query to retrieve infrastructure metrics",
        "parameters": {"query": "PromQL expression", "duration": "Time range (1h, 30m)"}
    },
    "search_logs": {
        "description": "Search recent log entries from Loki or journald",
        "parameters": {"pattern": "Search string", "host": "Hostname", "minutes": "Lookback"}
    },
    "run_ansible_adhoc": {
        "description": "Run an Ansible module on a host to gather live state",
        "parameters": {"host": "Target hostname", "module": "Module name", "args": "Arguments"}
    },
    "check_audit_log": {
        "description": "Query the self-healing and automation audit log",
        "parameters": {"host": "Hostname to check", "event_type": "Filter type (optional)"}
    },
    "get_recent_deployments": {
        "description": "Get recent CI/CD deployment events that may correlate with the issue",
        "parameters": {"service": "Service name", "hours": "Lookback hours"}
    },
}

MOCK_RESULTS = {
    "query_prometheus": json.dumps({
        "resultType": "vector",
        "result": [{
            "metric": {"instance": "node01:9100", "job": "node"},
            "value":  [1700000000, "94.3"]
        }]
    }),
    "search_logs": (
        "Nov 15 03:14:22 node01 kernel: Out of memory: Kill process 9876 (java) score 892\n"
        "Nov 15 03:14:23 node01 systemd[1]: app-server.service: Main process exited, "
        "code=killed, status=9/KILL\n"
        "Nov 15 03:14:24 node01 systemd[1]: app-server.service: Failed with result 'signal'."
    ),
    "run_ansible_adhoc": (
        "node01 | SUCCESS | rc=0 >>\n"
        "              total        used        free     shared\n"
        "Mem:           12.8G       12.1G        412M        0B\n"
        "Top memory process: java (PID 9876) 94.3% MEM 12.2GB RSS"
    ),
    "check_audit_log": (
        "2024-11-15T03:14:45Z MIGRATION_START batch=BATCH-01 host=node01 os=RHEL_9\n"
        "2024-11-15T03:15:30Z HEALED type=HighMemoryUsage host=node01 "
        "status=SUCCESS final_mem_pct=42"
    ),
    "get_recent_deployments": (
        "2024-11-15 02:45:00 UTC: app-server v2.1.4 → production (node01, node02, node03)\n"
        "Commit: 'Increase JVM heap from 4GB to 10GB for performance improvement'\n"
        "Deployed by: jenkins-ci | Duration: 8 minutes"
    ),
}


def execute_tool(tool_name: str, args: dict,
                 mock: bool = False,
                 prometheus_url: str = "http://localhost:9090") -> str:
    """Execute a tool call and return result as string."""
    if mock:
        result = MOCK_RESULTS.get(tool_name, f"[MOCK] {tool_name}: no mock data")
        log.debug(f"Mock result for {tool_name}: {result[:100]}...")
        return result

    if tool_name == "query_prometheus":
        try:
            import requests
            response = requests.get(
                f"{prometheus_url}/api/v1/query",
                params={"query": args.get("query", "up")},
                timeout=30
            )
            return json.dumps(response.json().get("data", {}))
        except Exception as e:
            return f"Prometheus query failed: {e}"

    elif tool_name == "run_ansible_adhoc":
        try:
            cmd = [
                "ansible", args.get("host", "localhost"),
                "-i", "inventory/",
                "-m", args.get("module", "ansible.builtin.shell"),
                "-a", args.get("args", "uptime"),
                "--become"
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            return result.stdout[:2000]
        except Exception as e:
            return f"Ansible ad-hoc failed: {e}"

    elif tool_name == "check_audit_log":
        try:
            audit_log = Path("/var/log/self_healing_audit.log")
            if not audit_log.exists():
                return "Self-healing audit log not found"
            host  = args.get("host", "")
            etype = args.get("event_type", "")
            lines = [l for l in audit_log.read_text().splitlines()
                     if host in l and (not etype or etype in l)]
            return "\n".join(lines[-20:]) or "No matching audit entries"
        except Exception as e:
            return f"Audit log check failed: {e}"

    return f"Tool '{tool_name}' not implemented for live mode"


class InfrastructureAgent:
    """Autonomous ReAct infrastructure investigation agent."""

    def __init__(self,
                 mock:           bool = False,
                 max_steps:      int  = 8,
                 prometheus_url: str  = "http://localhost:9090"):
        self.provider       = get_provider()
        self.mock           = mock
        self.max_steps      = max_steps
        self.prometheus_url = prometheus_url
        self.conversation:  list = []
        self.tool_calls:    list = []

    def investigate(self, goal: str) -> dict:
        """
        Autonomously investigate an infrastructure issue.

        Args:
            goal: Natural language investigation goal

        Returns:
            Investigation report dict with findings and recommendations
        """
        log.info(f"Investigation started: {goal}")
        started_at = datetime.now(timezone.utc)

        self.conversation = [
            {"role": "user", "content": f"Investigation goal: {goal}"}
        ]
        self.tool_calls = []

        for step in range(1, self.max_steps + 1):
            log.info(f"Step {step}/{self.max_steps}")

            # Ask the LLM for next action
            messages_str = json.dumps(self.conversation[-10:])  # Last 10 messages
            response = self.provider.generate(
                AGENT_SYSTEM_PROMPT,
                messages_str,
                temperature=0.0, max_tokens=1024
            )

            raw = response.content.strip()
            if raw.startswith("```"): raw = raw.split("\n", 1)[1]
            if raw.endswith("```"):   raw = raw.rsplit("\n", 1)[0]

            try:
                action = json.loads(raw.strip())
            except json.JSONDecodeError:
                log.warning(f"Could not parse agent response at step {step}")
                break

            # Check if investigation is complete
            if action.get("type") == "final_report":
                elapsed = (datetime.now(timezone.utc) - started_at).seconds
                log.info(f"Investigation complete in {step} steps, {elapsed}s")
                return self._build_report(goal, action, started_at, elapsed)

            # Execute tool
            tool_name = action.get("tool")
            tool_args = action.get("args", {})
            reasoning = action.get("reasoning", "")

            if tool_name not in TOOLS:
                log.warning(f"Unknown tool requested: {tool_name}")
                break

            log.info(f"  [{step}] {tool_name}({tool_args}) — {reasoning}")
            result = execute_tool(tool_name, tool_args,
                                  self.mock, self.prometheus_url)

            self.tool_calls.append({
                "step":      step,
                "tool":      tool_name,
                "args":      tool_args,
                "reasoning": reasoning,
                "result":    result[:500],
            })

            # Update conversation
            self.conversation.append({
                "role":    "assistant",
                "content": json.dumps(action)
            })
            self.conversation.append({
                "role":    "user",
                "content": f"Tool '{tool_name}' result:\n{result[:1500]}"
            })

        elapsed = (datetime.now(timezone.utc) - started_at).seconds
        return self._build_report(goal, {
            "findings": {"error": "Max investigation steps reached without conclusion",
                         "confidence": "low"}
        }, started_at, elapsed)

    def _build_report(self, goal: str, action: dict,
                      started_at: datetime, elapsed: int) -> dict:
        return {
            "goal":           goal,
            "investigated_at": started_at.isoformat(),
            "duration_seconds": elapsed,
            "steps_taken":    len(self.tool_calls),
            "mode":           "mock" if self.mock else "live",
            "tool_calls":     self.tool_calls,
            "findings":       action.get("findings", {}),
        }

    def print_report(self, report: dict) -> None:
        print(f"\n{'='*60}")
        print(f"INVESTIGATION REPORT")
        print(f"{'='*60}")
        print(f"Goal     : {report['goal']}")
        print(f"Duration : {report['duration_seconds']}s ({report['steps_taken']} steps)")
        print()
        findings = report.get("findings", {})
        if "error" in findings:
            print(f"Status   : INCOMPLETE — {findings['error']}")
        else:
            print(f"Root Cause: {findings.get('root_cause','Unknown')}")
            print(f"Confidence: {findings.get('confidence','unknown').upper()}")
            print(f"Timeline  : {findings.get('timeline','Unknown')}")
            print(f"Impact    : {findings.get('impact','Unknown')}")
            print(f"\nEvidence:")
            for e in findings.get("evidence", []):
                print(f"  • {e}")
            print(f"\nImmediate Fix: {findings.get('recommendation','')}")
            print(f"Prevention   : {findings.get('prevention','')}")

        print(f"\nTool calls ({len(report['tool_calls'])}):")
        for tc in report["tool_calls"]:
            print(f"  [{tc['step']}] {tc['tool']}: {tc['reasoning'][:60]}")


def main():
    parser = argparse.ArgumentParser(
        description="Autonomous infrastructure investigation agent"
    )
    parser.add_argument("--goal",       required=True,
                        help="Investigation goal in natural language")
    parser.add_argument("--mock",       action="store_true", default=True,
                        help="Use mock tool results (no live infrastructure needed)")
    parser.add_argument("--live",       action="store_true",
                        help="Use live infrastructure tools (overrides --mock)")
    parser.add_argument("--prometheus", default="http://localhost:9090")
    parser.add_argument("--max-steps",  type=int, default=8)
    parser.add_argument("--output",     help="Save report to JSON file")
    parser.add_argument("--json",       action="store_true")
    args = parser.parse_args()

    mock   = not args.live
    agent  = InfrastructureAgent(
        mock=mock, max_steps=args.max_steps,
        prometheus_url=args.prometheus
    )
    report = agent.investigate(args.goal)

    if args.output:
        Path(args.output).write_text(json.dumps(report, indent=2))
        log.info(f"Report saved: {args.output}")

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        agent.print_report(report)


if __name__ == "__main__":
    main()
