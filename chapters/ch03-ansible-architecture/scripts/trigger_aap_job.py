#!/usr/bin/env python3
"""
trigger_aap_job.py — Chapter 3, Listing 3-19
Trigger an Ansible Automation Platform Job Template via REST API.

Author : Balaramakrishna Alti
GitHub : https://github.com/balaramaa/ansible-aiops-playbook

Usage:
    export AAP_URL="https://aap.company.com"
    export AAP_USERNAME="ansible-svc"
    export AAP_PASSWORD="..."
    export JOB_TEMPLATE_ID="42"
    python3 trigger_aap_job.py
"""

import json, logging, os, sys, time
import requests
from requests.auth import HTTPBasicAuth

logging.basicConfig(level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s')
log = logging.getLogger(__name__)

AAP_URL     = os.environ.get("AAP_URL","").rstrip("/")
AAP_USER    = os.environ.get("AAP_USERNAME","")
AAP_PASS    = os.environ.get("AAP_PASSWORD","")
TEMPLATE_ID = os.environ.get("JOB_TEMPLATE_ID","42")

if not all([AAP_URL, AAP_USER, AAP_PASS]):
    log.error("Required: AAP_URL, AAP_USERNAME, AAP_PASSWORD")
    sys.exit(1)

session = requests.Session()
session.auth    = HTTPBasicAuth(AAP_USER, AAP_PASS)
session.headers.update({"Content-Type": "application/json"})
session.verify  = True


def trigger_job(template_id, extra_vars=None):
    url      = f"{AAP_URL}/api/v2/job_templates/{template_id}/launch/"
    payload  = {"extra_vars": json.dumps(extra_vars or {})}
    response = session.post(url, json=payload)
    response.raise_for_status()
    return response.json()


def wait_for_job(job_id, timeout=600):
    url   = f"{AAP_URL}/api/v2/jobs/{job_id}/"
    start = time.time()
    while time.time() - start < timeout:
        r = session.get(url); r.raise_for_status()
        status = r.json()["status"]
        if status in ("successful","failed","error","canceled"):
            return status
        log.info(f"Job {job_id}: {status}")
        time.sleep(15)
    return "timeout"


if __name__ == "__main__":
    extra_vars = {
        "target_host":      os.environ.get("TARGET_HOST","lab"),
        "remediation_type": os.environ.get("REMEDIATION_TYPE","linux_baseline"),
        "ticket_id":        os.environ.get("TICKET_ID","CHG0000000"),
    }
    job    = trigger_job(TEMPLATE_ID, extra_vars)
    status = wait_for_job(job["id"])
    log.info(f"Job {job['id']} finished: {status}")
    sys.exit(0 if status == "successful" else 1)
