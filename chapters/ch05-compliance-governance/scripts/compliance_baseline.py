#!/usr/bin/env python3
"""
compliance_baseline.py — Chapter 5, Listing 5-5
Collect and manage compliance baselines for drift detection.

Author : Balaramakrishna Alti
GitHub : https://github.com/balaramaa/ansible-aiops-playbook

Usage:
    python3 compliance_baseline.py --collect --host node01
    python3 compliance_baseline.py --detect  --host node01
    python3 compliance_baseline.py --fleet   --inventory inventory/
"""

import argparse, hashlib, json, logging, subprocess
from datetime import datetime, timezone
from pathlib import Path

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

BASELINE_DIR = Path("/var/lib/compliance/baselines")


def collect_baseline(hostname: str,
                     inventory: str = "inventory/",
                     profile: str = "cis_level1") -> dict:
    """Run compliance check in --check mode and fingerprint the result."""
    cmd = [
        "ansible-playbook",
        "-i", inventory,
        "--limit", hostname,
        "--check",
        "--tags", "cis",
        "-e", f"cis_level={profile}",
        "playbooks/compliance_check.yml"
    ]
    log.info(f"Collecting baseline for {hostname} (profile: {profile})")
    result = subprocess.run(cmd, capture_output=True, text=True)

    baseline = {
        "hostname":         hostname,
        "profile":          profile,
        "collected_at":     datetime.now(timezone.utc).isoformat(),
        "ansible_rc":       result.returncode,
        "controls_passed":  _parse_ok_count(result.stdout),
        "controls_failed":  _parse_changed_count(result.stdout),
        "fingerprint":      hashlib.sha256(result.stdout.encode()).hexdigest()[:16],
    }
    log.info(f"Baseline: passed={baseline['controls_passed']} "
             f"failed={baseline['controls_failed']} "
             f"fingerprint={baseline['fingerprint']}")
    return baseline


def save_baseline(baseline: dict) -> Path:
    BASELINE_DIR.mkdir(parents=True, exist_ok=True)
    path = BASELINE_DIR / f"{baseline['hostname']}.json"
    # Archive previous baseline
    if path.exists():
        prev = json.loads(path.read_text())
        archive = BASELINE_DIR / f"{baseline['hostname']}_{prev['collected_at'][:10]}.json"
        archive.write_text(json.dumps(prev, indent=2))
    path.write_text(json.dumps(baseline, indent=2))
    log.info(f"Baseline saved: {path}")
    return path


def load_baseline(hostname: str) -> dict | None:
    path = BASELINE_DIR / f"{hostname}.json"
    if not path.exists():
        log.warning(f"No baseline found for {hostname}")
        return None
    return json.loads(path.read_text())


def detect_drift(hostname: str, inventory: str = "inventory/") -> dict:
    """Collect current state and compare to baseline."""
    previous = load_baseline(hostname)
    if not previous:
        log.info(f"No previous baseline for {hostname} — collecting initial baseline")
        current = collect_baseline(hostname, inventory)
        save_baseline(current)
        return {"hostname": hostname, "drift_detected": False,
                "message": "Initial baseline collected — no drift possible yet"}

    current = collect_baseline(hostname, inventory)
    drift = {
        "hostname":            hostname,
        "detected_at":        current["collected_at"],
        "drift_detected":     False,
        "fingerprint_changed": current["fingerprint"] != previous["fingerprint"],
        "controls_delta": {
            "passed": current["controls_passed"] - previous["controls_passed"],
            "failed": current["controls_failed"] - previous["controls_failed"],
        },
        "current_fingerprint":  current["fingerprint"],
        "previous_fingerprint": previous["fingerprint"],
    }
    drift["drift_detected"] = (
        drift["fingerprint_changed"] or
        drift["controls_delta"]["failed"] > 0
    )

    if drift["drift_detected"]:
        log.warning(f"DRIFT DETECTED on {hostname}: "
                    f"fingerprint_changed={drift['fingerprint_changed']} "
                    f"new_failures={drift['controls_delta']['failed']}")
    else:
        log.info(f"No drift detected on {hostname}")

    # Save new baseline
    save_baseline(current)
    return drift


def _parse_ok_count(stdout: str) -> int:
    for line in stdout.splitlines():
        if "ok=" in line:
            try: return int(line.split("ok=")[1].split()[0])
            except: pass
    return 0


def _parse_changed_count(stdout: str) -> int:
    for line in stdout.splitlines():
        if "changed=" in line:
            try: return int(line.split("changed=")[1].split()[0])
            except: pass
    return 0


def main():
    parser = argparse.ArgumentParser(description="Compliance baseline management")
    parser.add_argument("--collect", action="store_true", help="Collect baseline")
    parser.add_argument("--detect",  action="store_true", help="Detect drift")
    parser.add_argument("--host",      required=True)
    parser.add_argument("--inventory", default="inventory/")
    parser.add_argument("--profile",   default="cis_level1")
    args = parser.parse_args()

    if args.collect:
        b = collect_baseline(args.host, args.inventory, args.profile)
        save_baseline(b)
        print(json.dumps(b, indent=2))
    elif args.detect:
        d = detect_drift(args.host, args.inventory)
        print(json.dumps(d, indent=2))
        if d.get("drift_detected"):
            exit(1)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
