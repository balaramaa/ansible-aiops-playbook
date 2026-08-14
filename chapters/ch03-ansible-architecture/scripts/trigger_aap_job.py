#!/usr/bin/env python3
"""
trigger_aap_job.py — Chapter 3, Listing 3-19
Trigger an Ansible Automation Platform Job Template via REST API.

Used in Chapter 7 for automated incident response integration with
ServiceNow and Event-Driven Ansible.

Author : Balaramakrishna Alti
GitHub : https://github.com/balaramaa/ansible-aiops-playbook

Requirements:
    pip3 install requests

Environment variables:
    AAP_URL          — https://aap.company.com
    AAP_USERNAME     — AAP service account username
    AAP_PASSWORD     — AAP service account password
    JOB_TEMPLATE_ID  — Job Template ID to launch (default: 42)

Usage:
    export AAP_URL="https://aap.company.com"
    export AAP_USERNAME="ansible-svc"
    export AAP_PASSWORD="..."
    export JOB_TEMPLATE_ID="42"
    python3 trigger_aap_job.py
"""

import os
import sys
import time
import json
import logging
import requests
from requests.auth import HTTPBasicAuth

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%dT%H:%M:%SZ'
)
log = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────────────
AAP_URL     = os.environ.get("AAP_URL", "").rstrip("/")
AAP_USER    = os.environ.get("AAP_USERNAME", "")
AAP_PASS    = os.environ.get("AAP_PASSWORD", "")
TEMPLATE_ID = os.environ.get("JOB_TEMPLATE_ID", "42")

if not all([AAP_URL, AAP_USER, AAP_PASS]):
    log.error("Required environment variables: AAP_URL, AAP_USERNAME, AAP_PASSWORD")
    sys.exit(1)

# ── Session setup ─────────────────────────────────────────────────────────────
session = requests.Session()
session.auth = HTTPBasicAuth(AAP_USER, AAP_PASS)
session.headers.update({"Content-Type": "application/json"})
session.verify = True  # Always verify SSL in production


def trigger_job(template_id: str, extra_vars: dict = None) -> dict:
    """
    Launch an AAP Job Template and return the job details.

    Args:
        template_id: The AAP Job Template ID to launch
        extra_vars:  Optional dict of extra variables to pass to the job

    Returns:
        Dict containing the launched job details (id, url, status)
    """
    url = f"{AAP_URL}/api/v2/job_templates/{template_id}/launch/"
    payload = {"extra_vars": json.dumps(extra_vars or {})}

    log.info(f"Launching Job Template {template_id} at {url}")
    response = session.post(url, json=payload)
    response.raise_for_status()
    data = response.json()
    log.info(f"Job {data['id']} launched successfully")
    return data


def wait_for_job(job_id: int, timeout: int = 600, poll_interval: int = 15) -> str:
    """
    Poll job status until complete or timeout.

    Args:
        job_id:        The AAP job ID to monitor
        timeout:       Maximum seconds to wait (default: 600)
        poll_interval: Seconds between status checks (default: 15)

    Returns:
        Final job status: 'successful', 'failed', 'error', 'canceled', 'timeout'
    """
    url = f"{AAP_URL}/api/v2/jobs/{job_id}/"
    start = time.time()
    terminal_statuses = {"successful", "failed", "error", "canceled"}

    while time.time() - start < timeout:
        response = session.get(url)
        response.raise_for_status()
        data = response.json()
        status = data["status"]

        log.info(f"Job {job_id} status: {status} "
                 f"(elapsed: {int(time.time() - start)}s)")

        if status in terminal_statuses:
            return status

        time.sleep(poll_interval)

    log.error(f"Job {job_id} timed out after {timeout}s")
    return "timeout"


def get_job_output(job_id: int) -> str:
    """Retrieve the stdout output of a completed job."""
    url = f"{AAP_URL}/api/v2/jobs/{job_id}/stdout/?format=txt"
    response = session.get(url)
    response.raise_for_status()
    return response.text


if __name__ == "__main__":
    # Example: trigger remediation job for SSH hardening
    extra_vars = {
        "target_host": os.environ.get("TARGET_HOST", "lab"),
        "remediation_type": os.environ.get("REMEDIATION_TYPE", "linux_baseline"),
        "ticket_id": os.environ.get("TICKET_ID", "CHG0000000"),
    }

    log.info(f"Extra vars: {json.dumps(extra_vars, indent=2)}")

    try:
        job = trigger_job(TEMPLATE_ID, extra_vars)
        job_id = job["id"]
        job_url = f"{AAP_URL}/#/jobs/{job_id}/output"
        log.info(f"Job URL: {job_url}")

        final_status = wait_for_job(job_id)

        if final_status == "successful":
            log.info(f"✔ Job {job_id} completed successfully")
            sys.exit(0)
        else:
            log.error(f"✗ Job {job_id} ended with status: {final_status}")
            # Retrieve output for debugging
            output = get_job_output(job_id)
            print("\n--- Job Output (last 50 lines) ---")
            print("\n".join(output.splitlines()[-50:]))
            sys.exit(1)

    except requests.exceptions.RequestException as e:
        log.error(f"AAP API error: {e}")
        sys.exit(1)
