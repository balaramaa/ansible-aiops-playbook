#!/usr/bin/env python3
"""
ai_decision_engine.py — Chapter 13, Listing 13-4
AIOps platform AI decision engine.

Author : Balaramakrishna Alti
GitHub : https://github.com/balaramaa/ansible-aiops-playbook

Usage:
    # Run in mock mode (no Redis or LLM required for lab)
    python3 ai_decision_engine.py --mock

    # Run against live event bus
    export REDIS_URL=redis://localhost:6379
    export OPENAI_API_KEY=...
    python3 ai_decision_engine.py

    # Test with a single simulated event
    python3 ai_decision_engine.py --mock --test-event memory
"""

import argparse, json, logging, subprocess, sys, time
from collections import defaultdict
from datetime import datetime, timezone, timedelta

sys.path.insert(0, ".")
sys.path.insert(0, "../../ch04-llm-playbook-generation/scripts")

from event_bus import EventBus
from llm_provider import get_provider

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
log = logging.getLogger("aiops.engine")

ORCHESTRATOR_PROMPT = """
You are an AIOps orchestration engine for enterprise Linux infrastructure.
Given correlated infrastructure events, determine the optimal response strategy.
Return ONLY this JSON:

{
  "incident_type": "infrastructure|security|compliance|performance|cascade",
  "root_cause_host": "<hostname or null>",
  "blast_radius": "single_host|service|environment|fleet",
  "recommended_actions": [
    {
      "action": "run_playbook|trigger_eda|create_itsm|escalate|monitor_only",
      "target": "<hostname or ansible group>",
      "playbook": "<relative playbook path or null>",
      "priority": 1,
      "rationale": "Why this action addresses the root cause"
    }
  ],
  "auto_execute": true|false,
  "escalate_reason": "<reason if auto_execute=false, else null>",
  "estimated_resolution_minutes": <int>,
  "prevent_recurrence": "Long-term recommendation to prevent this incident type"
}

Decision rules for auto_execute:
  true  → Known pattern + single_host/service blast radius + high confidence
  false → Novel pattern, fleet-wide impact, security incident, or low confidence

Playbook mapping:
  HighMemoryUsage   → playbooks/remediate_memory.yml
  DiskSpaceCritical → playbooks/remediate_disk.yml
  ServiceDown       → playbooks/remediate_service.yml
  compliance_drift  → chapters/ch05-compliance-governance/playbooks/compliance_remediate.yml
  security_threat   → chapters/ch08-security-automation/playbooks/isolate_host.yml
"""

TEST_EVENTS = {
    "memory": {
        "event_type": "alert", "hostname": "node02.company.com",
        "severity": "critical", "environment": "production",
        "payload": {"alert_name": "HighMemoryUsage", "current_value": 94.2,
                    "threshold": 90.0},
        "source": "prometheus", "auto_remediate": True,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "correlation_id": "INC-node02-test", "ttl_seconds": 3600,
    },
    "compliance": {
        "event_type": "compliance_drift", "hostname": "node03.company.com",
        "severity": "high", "environment": "production",
        "payload": {"control_id": "ssh_config", "drift_type": "PermitRootLogin",
                    "expected": "no", "actual": "yes"},
        "source": "openscap", "auto_remediate": True,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "correlation_id": "INC-node03-test", "ttl_seconds": 3600,
    },
    "security": {
        "event_type": "security_threat", "hostname": "node04.company.com",
        "severity": "critical", "environment": "production",
        "payload": {"threat_level": "critical", "attack_pattern": "privilege_escalation",
                    "description": "Unexpected setuid call by unknown process"},
        "source": "ebpf_analyzer", "auto_remediate": False,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "correlation_id": "INC-node04-test", "ttl_seconds": 3600,
    },
}


class IncidentCorrelator:
    """Groups related events from the same host within a time window."""

    def __init__(self, window_minutes: int = 5):
        self.window    = timedelta(minutes=window_minutes)
        self.incidents: dict = defaultdict(list)

    def add_event(self, event: dict) -> str:
        host      = event.get("hostname", "unknown")
        timestamp = datetime.fromisoformat(
            event["timestamp"].replace("Z", "+00:00"))

        for incident_id, events in self.incidents.items():
            last_ts = datetime.fromisoformat(
                events[-1]["timestamp"].replace("Z", "+00:00"))
            if (events[0].get("hostname") == host and
                    timestamp - last_ts <= self.window):
                events.append(event)
                log.debug(f"Event added to incident {incident_id} "
                          f"({len(events)} events)")
                return incident_id

        incident_id = event.get("correlation_id",
            f"INC-{host.split('.')[0]}-{timestamp.strftime('%Y%m%d%H%M%S')}")
        self.incidents[incident_id] = [event]
        log.info(f"New incident: {incident_id}")
        return incident_id

    def get_incident(self, incident_id: str) -> list:
        return self.incidents.get(incident_id, [])


class AIDecisionEngine:
    """Main AIOps decision engine — correlates events and orchestrates responses."""

    def __init__(self,
                 event_bus:      EventBus,
                 inventory_path: str  = "inventory/",
                 mock:           bool = False):
        self.bus        = event_bus
        self.inventory  = inventory_path
        self.correlator = IncidentCorrelator()
        self.provider   = get_provider()
        self.mock       = mock
        self.stats      = defaultdict(int)

    def process_event(self, event: dict) -> dict | None:
        """
        Process a platform event. Returns action plan or None.
        Analyzes after first critical/high event or after 3+ correlated events.
        """
        self.stats["events_received"] += 1
        incident_id = self.correlator.add_event(event)
        incident    = self.correlator.get_incident(incident_id)
        severity    = event.get("severity", "low")

        should_analyze = (
            severity in ("critical", "high") or
            len(incident) >= 3
        )

        if not should_analyze:
            log.debug(f"Event buffered: {incident_id} ({len(incident)} events)")
            return None

        log.info(f"Analyzing incident {incident_id} ({len(incident)} events, "
                 f"severity={severity})")

        plan = self._ai_orchestrate(incident, incident_id)
        self.stats["incidents_analyzed"] += 1

        if plan.get("auto_execute"):
            self._execute_plan(plan, incident_id)
            self.stats["auto_executed"] += 1
        else:
            self._escalate(plan, incident_id)
            self.stats["escalated"] += 1

        return plan

    def _ai_orchestrate(self, events: list, incident_id: str) -> dict:
        """Use AI to determine optimal response strategy."""
        if self.mock:
            return self._mock_plan(events, incident_id)

        prompt = f"""Analyze this infrastructure incident:

Incident ID: {incident_id}
Event count: {len(events)}
Severity:    {events[-1].get('severity','unknown')}

Events:
{json.dumps(events, indent=2)}

Determine incident type, root cause, and optimal response."""

        response = self.provider.generate(
            ORCHESTRATOR_PROMPT, prompt,
            temperature=0.0, max_tokens=1024
        )
        raw = response.content.strip()
        if raw.startswith("```"): raw = raw.split("\n", 1)[1]
        if raw.endswith("```"):   raw = raw.rsplit("\n", 1)[0]
        plan = json.loads(raw.strip())
        plan["incident_id"] = incident_id
        return plan

    def _mock_plan(self, events: list, incident_id: str) -> dict:
        """Generate a realistic mock action plan for lab exercises."""
        event      = events[-1]
        event_type = event.get("event_type", "alert")
        payload    = event.get("payload", {})
        alert_name = payload.get("alert_name", "")
        severity   = event.get("severity", "medium")
        hostname   = event.get("hostname", "unknown")

        playbook_map = {
            "HighMemoryUsage":   "playbooks/remediate_memory.yml",
            "DiskSpaceCritical": "playbooks/remediate_disk.yml",
            "ServiceDown":       "playbooks/remediate_service.yml",
        }

        auto_exec  = event_type != "security_threat" and severity != "critical"
        playbook   = playbook_map.get(alert_name)
        action_type = "run_playbook" if playbook else "escalate"

        return {
            "incident_id":     incident_id,
            "incident_type":   "infrastructure",
            "root_cause_host": hostname,
            "blast_radius":    "single_host",
            "recommended_actions": [{
                "action":    action_type,
                "target":    hostname,
                "playbook":  playbook,
                "priority":  1,
                "rationale": f"[MOCK] Auto-remediate {alert_name or event_type}",
            }],
            "auto_execute":                    auto_exec,
            "escalate_reason":                 None if auto_exec else "Mock: security events always escalate",
            "estimated_resolution_minutes":    2,
            "prevent_recurrence":              "[MOCK] Review resource allocation and capacity planning",
        }

    def _execute_plan(self, plan: dict, incident_id: str) -> None:
        """Execute auto-approved remediation actions."""
        log.info(f"Executing plan for {incident_id}: "
                 f"{plan.get('incident_type')} / {plan.get('blast_radius')}")

        for action in sorted(plan.get("recommended_actions", []),
                             key=lambda a: a.get("priority", 99)):
            act = action.get("action", "")
            log.info(f"  Action: {act} → {action.get('target')} "
                     f"({action.get('rationale','')})")

            if act == "run_playbook" and action.get("playbook"):
                self._run_playbook(
                    action["playbook"],
                    action.get("target", ""),
                    {"incident_id": incident_id, "auto_remediate": True},
                )
            elif act == "create_itsm":
                self._create_itsm_record(plan, incident_id)
            elif act == "escalate":
                self._escalate(plan, incident_id)

    def _run_playbook(self, playbook: str, limit: str,
                      extra_vars: dict) -> None:
        """Execute Ansible playbook. Logs in mock mode."""
        if self.mock:
            log.info(f"[MOCK] ansible-playbook {playbook} --limit {limit}")
            return

        cmd = [
            "ansible-playbook",
            "-i", self.inventory,
            "--limit", limit,
            "-e", json.dumps(extra_vars),
            playbook,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            log.error(f"Playbook FAILED: {playbook} rc={result.returncode}")
            log.error(result.stderr[:300])
        else:
            log.info(f"Playbook succeeded: {playbook} / {limit}")

    def _escalate(self, plan: dict, incident_id: str) -> None:
        """Escalate incident to human operators via event bus."""
        reason = plan.get("escalate_reason", "Manual review required")
        log.warning(f"ESCALATION: {incident_id} — {reason}")
        self.bus.publish(
            event_type=     "escalation",
            hostname=       plan.get("root_cause_host", "unknown"),
            severity=       "high",
            payload={
                "incident_id":          incident_id,
                "incident_type":        plan.get("incident_type"),
                "escalate_reason":      reason,
                "recommended_actions":  plan.get("recommended_actions", []),
            },
            source=         "ai_decision_engine",
            auto_remediate= False,
        )

    def _create_itsm_record(self, plan: dict, incident_id: str) -> None:
        """Create ITSM ticket. Delegates to escalate_incident.yml playbook."""
        log.info(f"Creating ITSM record for {incident_id}")
        if not self.mock:
            self._run_playbook(
                "playbooks/escalate_incident.yml",
                plan.get("root_cause_host", "localhost"),
                {
                    "incident_id":    incident_id,
                    "incident_type":  plan.get("incident_type", "unknown"),
                    "alert_name":     incident_id,
                },
            )

    def print_stats(self) -> None:
        print(f"\nAI Decision Engine Statistics")
        print(f"{'='*40}")
        for k, v in self.stats.items():
            print(f"  {k:<28}: {v}")

    def run(self) -> None:
        """Main event processing loop — runs until interrupted."""
        log.info("AI Decision Engine started — listening for platform events")
        log.info(f"Mode: {'MOCK' if self.mock else 'LIVE'}")
        try:
            for event in self.bus.subscribe("ai-decision-engine"):
                plan = self.process_event(event)
                if plan:
                    log.info(
                        f"Plan: {plan['incident_type']} | "
                        f"auto={plan['auto_execute']} | "
                        f"ETA={plan.get('estimated_resolution_minutes')}min"
                    )
        except KeyboardInterrupt:
            log.info("Engine stopped by user")
        finally:
            self.print_stats()


def main():
    parser = argparse.ArgumentParser(description="AIOps AI Decision Engine")
    parser.add_argument("--mock",       action="store_true", default=True)
    parser.add_argument("--inventory",  default="inventory/")
    parser.add_argument("--test-event", choices=list(TEST_EVENTS.keys()),
                        help="Process a single test event and exit")
    args = parser.parse_args()

    bus    = EventBus(mock=args.mock)
    engine = AIDecisionEngine(bus, inventory_path=args.inventory, mock=args.mock)

    if args.test_event:
        event = TEST_EVENTS[args.test_event]
        log.info(f"Processing test event: {args.test_event}")
        plan = engine.process_event(event)
        if plan:
            print(json.dumps(plan, indent=2))
        engine.print_stats()
    else:
        # Publish some test events in mock mode to demonstrate
        if args.mock:
            for name, event in TEST_EVENTS.items():
                bus._mock_queue.append(event)
        engine.run()


if __name__ == "__main__":
    main()
