#!/usr/bin/env python3
"""
satellite_client.py — Chapter 6, Listing 6-1
Red Hat Satellite API client for errata and host queries.

Author : Balaramakrishna Alti
GitHub : https://github.com/balaramaa/ansible-aiops-playbook

Environment variables:
    SATELLITE_URL   — https://satellite.company.com
    SATELLITE_USER  — API username (recommend a dedicated service account)
    SATELLITE_PASS  — API password
    SATELLITE_MOCK  — Set to "true" for lab use without a real Satellite

Usage:
    from satellite_client import SatelliteClient
    client = SatelliteClient(mock=True)   # Lab mode
    errata = client.get_applicable_errata()
    for e in errata:
        print(f"{e.errata_id}: {e.severity} — {e.hosts_count} hosts affected")
"""

import json, logging, os
import requests
from requests.auth import HTTPBasicAuth
from dataclasses import dataclass, field

log = logging.getLogger(__name__)


@dataclass
class Erratum:
    """Represents a single Red Hat erratum (security advisory, bug fix, etc.)"""
    errata_id:    str         # e.g., RHSA-2024:1234
    errata_type:  str         # security | bugfix | enhancement
    severity:     str         # Critical | Important | Moderate | Low
    title:        str
    cves:         list        # e.g., ['CVE-2024-1234']
    packages:     list        # Affected package filenames
    hosts_count:  int = 0     # How many managed hosts need this erratum


class SatelliteClient:
    """
    Red Hat Satellite 6/7 API client.

    Supports mock mode for lab exercises — set mock=True or
    SATELLITE_MOCK=true to use realistic sample data without
    requiring a real Satellite server.
    """

    def __init__(self,
                 url: str = None,
                 username: str = None,
                 password: str = None,
                 mock: bool = False):
        self.url      = url      or os.environ.get("SATELLITE_URL", "")
        self.username = username or os.environ.get("SATELLITE_USER", "")
        self.password = password or os.environ.get("SATELLITE_PASS", "")
        self.mock     = (mock or
                         os.environ.get("SATELLITE_MOCK", "false").lower() == "true")

        if not self.mock and not self.url:
            raise ValueError(
                "SATELLITE_URL not set. Set SATELLITE_MOCK=true for lab mode.")

        self.session = requests.Session()
        self.session.auth    = HTTPBasicAuth(self.username, self.password)
        self.session.verify  = True
        self.session.headers.update({
            "Content-Type": "application/json",
            "Accept":       "application/json",
        })

    def get_applicable_errata(self,
                               organization: str = "Default Organization",
                               errata_type: str = None,
                               severity: str = None) -> list:
        """
        Retrieve applicable errata for the organization.

        Args:
            organization: Satellite organization name
            errata_type:  Filter by type: security | bugfix | enhancement
            severity:     Filter by severity: Critical | Important | Moderate | Low

        Returns:
            List of Erratum objects sorted by severity
        """
        if self.mock:
            return self._mock_errata(errata_type, severity)

        params = {
            "organization": organization,
            "per_page":     200,
            "page":         1,
        }
        if errata_type: params["errata_type"] = errata_type
        if severity:    params["severity"]    = severity

        url = f"{self.url}/katello/api/errata"
        response = self.session.get(url, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()

        errata = []
        for e in data.get("results", []):
            errata.append(Erratum(
                errata_id   = e["errata_id"],
                errata_type = e.get("errata_type", ""),
                severity    = e.get("severity", "Unknown"),
                title       = e.get("title", ""),
                cves        = [c["cve_id"] for c in e.get("cves", [])],
                packages    = [p["filename"] for p in e.get("packages", [])],
                hosts_count = e.get("hosts_applicable_count", 0),
            ))

        log.info(f"Retrieved {len(errata)} errata from Satellite")
        # Sort: Critical first, then by hosts affected
        severity_order = {"Critical": 0, "Important": 1,
                          "Moderate": 2, "Low": 3, "Unknown": 4}
        errata.sort(key=lambda e: (
            severity_order.get(e.severity, 4), -e.hosts_count))
        return errata

    def get_hosts_needing_erratum(self, errata_id: str) -> list:
        """Return hosts that need a specific erratum applied."""
        if self.mock:
            return [
                {"name": "node01", "ip": "192.168.1.11", "id": 1},
                {"name": "node02", "ip": "192.168.1.12", "id": 2},
                {"name": "node03", "ip": "192.168.1.13", "id": 3},
            ]

        url = f"{self.url}/api/hosts"
        params = {
            "search":   f"applicable_errata={errata_id}",
            "per_page": 500,
        }
        response = self.session.get(url, params=params, timeout=30)
        response.raise_for_status()
        return response.json().get("results", [])

    def trigger_errata_install(self,
                                host_ids: list,
                                errata_ids: list) -> int:
        """
        Trigger errata installation via Satellite Remote Execution.

        Returns:
            Satellite job invocation ID
        """
        if self.mock:
            job_id = 9999
            log.info(f"[MOCK] Would install {len(errata_ids)} errata "
                     f"on {len(host_ids)} hosts — mock job ID: {job_id}")
            return job_id

        url = f"{self.url}/api/job_invocations"
        payload = {
            "job_invocation": {
                "job_category":  "Katello",
                "feature":       "katello_errata_install",
                "inputs":        {"errata": ",".join(errata_ids)},
                "targeting_type":"static_query",
                "bookmark_id":   None,
                "host_ids":      host_ids,
            }
        }
        response = self.session.post(url, json=payload, timeout=30)
        response.raise_for_status()
        job_id = response.json()["id"]
        log.info(f"Satellite patch job created: {job_id}")
        return job_id

    def _mock_errata(self, errata_type=None, severity=None) -> list:
        """Return realistic mock errata for lab exercises."""
        all_errata = [
            Erratum("RHSA-2024:0001", "security", "Critical",
                    "Critical: kernel security and bug fix update",
                    ["CVE-2024-1234", "CVE-2024-1235"],
                    ["kernel-5.14.0-362.el9.x86_64.rpm",
                     "kernel-core-5.14.0-362.el9.x86_64.rpm"], 847),
            Erratum("RHSA-2024:0002", "security", "Important",
                    "Important: openssl security update",
                    ["CVE-2024-2345"],
                    ["openssl-3.0.7-27.el9.x86_64.rpm",
                     "openssl-libs-3.0.7-27.el9.x86_64.rpm"], 3200),
            Erratum("RHSA-2024:0003", "security", "Moderate",
                    "Moderate: curl security update",
                    ["CVE-2024-3456"],
                    ["curl-7.76.1-29.el9.x86_64.rpm"], 4500),
            Erratum("RHSA-2024:0004", "security", "Low",
                    "Low: python3-pip security update",
                    ["CVE-2024-4567"],
                    ["python3-pip-21.3.1-1.el9.noarch.rpm"], 2100),
            Erratum("RHBA-2024:0010", "bugfix", "",
                    "Bug fix: systemd reliability improvements",
                    [],
                    ["systemd-252-32.el9.x86_64.rpm"], 4500),
        ]
        if errata_type:
            all_errata = [e for e in all_errata if e.errata_type == errata_type]
        if severity:
            all_errata = [e for e in all_errata if e.severity == severity]
        return all_errata
