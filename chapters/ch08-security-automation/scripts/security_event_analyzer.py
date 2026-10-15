#!/usr/bin/env python3
"""
security_event_analyzer.py — Chapter 8, Listing 8-3
AI-powered security event classification from eBPF stream.

Author : Balaramakrishna Alti
GitHub : https://github.com/balaramaa/ansible-aiops-playbook

Usage:
    # Process live eBPF stream
    sudo bpftrace ebpf-security/detect_privilege_escalation.bt | \\
        python3 security_event_analyzer.py

    # Test with a simulated event
    python3 security_event_analyzer.py --test-event privilege_escalation

    # Read from JSON log file
    python3 security_event_analyzer.py --file /var/log/security_events.jsonl
"""

import argparse, json, logging, sys, time
from collections import defaultdict, deque
from datetime import datetime, timezone

sys.path.insert(0, "../../ch04-llm-playbook-generation/scripts")
from llm_provider import get_provider

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

SECURITY_ANALYST_PROMPT = """
You are a Linux security analyst monitoring eBPF kernel security events.
Analyze the provided events and return ONLY this JSON structure:

{
  "threat_level": "critical|high|medium|low|benign",
  "attack_pattern": "privilege_escalation|lateral_movement|data_exfiltration|
                     persistence|reconnaissance|credential_access|benign_activity",
  "confidence": "high|medium|low",
  "description": "What is happening in plain English (one sentence)",
  "ioc": ["Indicator of compromise 1", "IOC 2"],
  "immediate_action": "What to do right now",
  "auto_respond": true|false,
  "auto_response_action": "block_network|isolate_host|kill_process|alert_only|none"
}

False positive reduction context:
- sudo, su: NORMAL privilege operations
- sshd: NORMAL SSH daemon operations  
- systemd, init: NORMAL system management
- dnf, rpm, yum: NORMAL package management
- ansible SSH connections (user=ansible): NORMAL automation
- Scheduled cron jobs: NORMAL at expected times
- Kernel threads (kworker, ksoftirqd): NORMAL

Escalate (auto_respond=false) when:
- Novel attack patterns not matching known-good baselines
- Multiple related events suggesting coordinated attack
- Root processes with unexpected executable paths
"""

MOCK_EVENTS = {
    "privilege_escalation": [
        {"event": "PRIV_ESC_ATTEMPT", "timestamp": 1234567890, "pid": 9876,
         "ppid": 9875, "comm": "exploit_kit", "target_uid": 0},
        {"event": "ROOT_EXEC", "timestamp": 1234567891, "pid": 9876,
         "comm": "exploit_kit", "exe": "/tmp/.hidden/shell"},
    ],
    "sensitive_write": [
        {"event": "SENSITIVE_FILE_WRITE", "timestamp": 1234567890,
         "pid": 1234, "comm": "python3", "file": "passwd"},
    ],
    "normal": [
        {"event": "ROOT_EXEC", "timestamp": 1234567890, "pid": 100,
         "comm": "sudo", "exe": "/usr/bin/dnf"},
    ]
}


class SecurityEventWindow:
    """Sliding window of recent events for correlation."""

    def __init__(self, window_size: int = 50, analysis_threshold: int = 3):
        self.events    = deque(maxlen=window_size)
        self.counts    = defaultdict(int)
        self.threshold = analysis_threshold

    def add(self, event: dict) -> None:
        self.events.append(event)
        self.counts[event.get("event", "")] += 1

    def should_analyze(self, event: dict) -> bool:
        etype = event.get("event", "")
        comm  = event.get("comm", "")

        # Always analyze these high-value events
        if etype in ("PRIV_ESC_ATTEMPT", "SENSITIVE_FILE_WRITE", "RAW_SOCKET"):
            return True
        # Analyze root exec from non-standard processes
        if etype == "ROOT_EXEC" and comm not in (
            "sudo", "su", "sshd", "systemd", "crond", "dnf", "rpm",
            "ansible", "python3", "bash", "sh"
        ):
            return True
        # Analyze rapid repeated events
        if self.counts.get(etype, 0) >= self.threshold:
            self.counts[etype] = 0  # Reset counter
            return True
        return False


def analyze_events(events: list, provider=None) -> dict:
    """Use AI to classify a batch of security events."""
    if provider is None:
        provider = get_provider()

    prompt = f"""Analyze these security events from an enterprise Linux server:

{json.dumps(events, indent=2)}

Classify the threat level and recommended response."""

    response = provider.generate(
        SECURITY_ANALYST_PROMPT, prompt,
        temperature=0.0, max_tokens=512
    )
    raw = response.content.strip()
    if raw.startswith("```"): raw = raw.split("\n", 1)[1]
    if raw.endswith("```"):   raw = raw.rsplit("\n", 1)[0]

    analysis = json.loads(raw.strip())
    analysis["analyzed_at"] = datetime.now(timezone.utc).isoformat()
    analysis["model"]        = response.model
    return analysis


def send_eda_event(hostname: str, analysis: dict) -> None:
    """Send security threat to EDA for automated response."""
    try:
        import requests
        payload = {
            "payload": {
                "event_type":     "security_threat",
                "hostname":       hostname,
                "threat_level":   analysis["threat_level"],
                "attack_pattern": analysis["attack_pattern"],
                "auto_respond":   analysis["auto_respond"],
                "action":         analysis["auto_response_action"],
                "timestamp":      analysis["analyzed_at"],
            }
        }
        requests.post("http://localhost:8000/endpoint",
                      json=payload, timeout=5)
        log.info(f"EDA event sent: {analysis['threat_level']} / "
                 f"{analysis['attack_pattern']}")
    except Exception as e:
        log.error(f"Failed to send EDA event: {e}")


def process_stream(stream, hostname: str = "localhost") -> None:
    """Process security events from stdin or file."""
    window   = SecurityEventWindow()
    provider = get_provider()

    for line in stream:
        line = line.strip()
        if not line or not line.startswith("{"):
            continue
        try:
            event = json.loads(line)
            event["hostname"] = hostname
            window.add(event)

            if window.should_analyze(event):
                log.info(f"Analyzing event: {event.get('event')}")
                analysis = analyze_events(list(window.events), provider)

                level = analysis.get("threat_level", "benign")
                if level in ("critical", "high"):
                    log.warning(
                        f"🚨 SECURITY ALERT [{level.upper()}]: "
                        f"{analysis.get('description', '')}"
                    )
                    if analysis.get("auto_respond"):
                        send_eda_event(hostname, analysis)
                elif level == "medium":
                    log.warning(
                        f"⚠ Security notice [{level}]: "
                        f"{analysis.get('description', '')}"
                    )
                else:
                    log.debug(f"Benign event classified: {event.get('event')}")

        except json.JSONDecodeError:
            continue
        except Exception as e:
            log.error(f"Analysis error: {e}")


def main():
    parser = argparse.ArgumentParser(description="AI security event analyzer")
    parser.add_argument("--file", help="Process events from JSON log file")
    parser.add_argument("--test-event",
                        choices=["privilege_escalation", "sensitive_write", "normal"],
                        help="Run with mock test events")
    parser.add_argument("--hostname", default="localhost")
    args = parser.parse_args()

    if args.test_event:
        events   = MOCK_EVENTS[args.test_event]
        analysis = analyze_events(events)
        print(f"\nTest Event: {args.test_event}")
        print(f"{'='*50}")
        print(json.dumps(analysis, indent=2))
    elif args.file:
        with open(args.file) as f:
            process_stream(f, args.hostname)
    else:
        log.info("Reading security events from stdin...")
        process_stream(sys.stdin, args.hostname)


if __name__ == "__main__":
    main()
