#!/usr/bin/env python3
"""
nvd_client.py — Chapter 6, Listing 6-3
NVD and CISA KEV API client for CVE intelligence.

Author : Balaramakrishna Alti
GitHub : https://github.com/balaramaa/ansible-aiops-playbook

Environment variables:
    NVD_API_KEY  — Optional NVD API key (10 req/min without, 50 req/min with)

Usage:
    from nvd_client import get_cve_details, is_exploited

    details = get_cve_details("CVE-2024-1234")
    print(f"CVSS: {details['cvss_score']}, Days old: {details['days_since_pub']}")
    print(f"Actively exploited: {is_exploited('CVE-2024-1234')}")
"""

import json, logging, os, time
from datetime import datetime, timezone
from pathlib import Path
import requests

log = logging.getLogger(__name__)

NVD_API_URL = "https://services.nvd.nist.gov/rest/json/cves/2.0"
KEV_URL     = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"

CACHE_DIR   = Path("/var/cache/cve-intelligence")
KEV_CACHE   = CACHE_DIR / "kev.json"
NVD_CACHE   = CACHE_DIR / "nvd"
KEV_MAX_AGE = 3600   # Refresh KEV every hour
NVD_MAX_AGE = 86400  # Cache NVD data for 24 hours


def get_cve_details(cve_id: str) -> dict:
    """
    Retrieve CVE details from NVD API.

    Returns dict with:
        cve_id, found, cvss_score, published, days_since_pub, description
    """
    # Check NVD cache first
    NVD_CACHE.mkdir(parents=True, exist_ok=True)
    cache_file = NVD_CACHE / f"{cve_id}.json"
    if cache_file.exists():
        age = time.time() - cache_file.stat().st_mtime
        if age < NVD_MAX_AGE:
            log.debug(f"NVD cache hit: {cve_id}")
            return json.loads(cache_file.read_text())

    api_key = os.environ.get("NVD_API_KEY", "")
    headers = {"apiKey": api_key} if api_key else {}

    # NVD rate limit: be polite
    time.sleep(0.6 if not api_key else 0.1)

    try:
        response = requests.get(
            f"{NVD_API_URL}?cveId={cve_id}",
            headers=headers, timeout=30
        )
        response.raise_for_status()
    except requests.RequestException as e:
        log.error(f"NVD API error for {cve_id}: {e}")
        return {"cve_id": cve_id, "found": False,
                "cvss_score": 0.0, "days_since_pub": 0,
                "description": "NVD API unavailable", "error": str(e)}

    data  = response.json()
    vulns = data.get("vulnerabilities", [])
    if not vulns:
        return {"cve_id": cve_id, "found": False}

    cve     = vulns[0]["cve"]
    metrics = cve.get("metrics", {})

    # Prefer CVSSv3.1 > CVSSv3.0 > CVSSv2
    cvss_score = 0.0
    for key in ["cvssMetricV31", "cvssMetricV30", "cvssMetricV2"]:
        if key in metrics:
            cvss_score = float(metrics[key][0]["cvssData"]["baseScore"])
            break

    pub_date    = cve.get("published", "")[:10]
    pub_dt      = datetime.strptime(pub_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    days_since  = (datetime.now(timezone.utc) - pub_dt).days
    description = ""
    for d in cve.get("descriptions", []):
        if d.get("lang") == "en":
            description = d["value"][:300]
            break

    result = {
        "cve_id":         cve_id,
        "found":          True,
        "cvss_score":     cvss_score,
        "published":      pub_date,
        "days_since_pub": days_since,
        "description":    description,
    }

    cache_file.write_text(json.dumps(result))
    return result


def get_kev_catalog(force_refresh: bool = False) -> set:
    """
    Return set of CVE IDs in the CISA Known Exploited Vulnerabilities catalog.
    CVEs in KEV are actively exploited in the wild — highest exploit score.
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    if not force_refresh and KEV_CACHE.exists():
        age = time.time() - KEV_CACHE.stat().st_mtime
        if age < KEV_MAX_AGE:
            data    = json.loads(KEV_CACHE.read_text())
            cve_ids = {v["cveID"] for v in data.get("vulnerabilities", [])}
            log.debug(f"KEV cache hit: {len(cve_ids)} CVEs")
            return cve_ids

    log.info("Refreshing CISA KEV catalog...")
    try:
        response = requests.get(KEV_URL, timeout=30)
        response.raise_for_status()
        data = response.json()
        KEV_CACHE.write_text(json.dumps(data))
        cve_ids = {v["cveID"] for v in data.get("vulnerabilities", [])}
        log.info(f"KEV catalog refreshed: {len(cve_ids)} known-exploited CVEs")
        return cve_ids
    except requests.RequestException as e:
        log.error(f"Could not fetch CISA KEV: {e}")
        # Return cached data even if stale
        if KEV_CACHE.exists():
            data = json.loads(KEV_CACHE.read_text())
            return {v["cveID"] for v in data.get("vulnerabilities", [])}
        return set()


def is_exploited(cve_id: str) -> bool:
    """
    Check if a CVE is in the CISA KEV (actively exploited in the wild).
    This is the highest-weight exploit indicator in the risk scoring model.
    """
    return cve_id in get_kev_catalog()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="CVE intelligence lookup")
    parser.add_argument("--cve", required=True)
    args = parser.parse_args()

    details   = get_cve_details(args.cve)
    exploited = is_exploited(args.cve)
    details["in_cisa_kev"] = exploited
    print(json.dumps(details, indent=2))
