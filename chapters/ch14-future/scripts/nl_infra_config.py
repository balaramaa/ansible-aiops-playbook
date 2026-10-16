#!/usr/bin/env python3
"""
nl_infra_config.py — Chapter 14, Listing 14-2
Natural language to complete infrastructure configuration pipeline.

Author : Balaramakrishna Alti
GitHub : https://github.com/balaramaa/ansible-aiops-playbook

Usage:
    # Generate playbook from natural language intent (mock mode)
    python3 nl_infra_config.py \
        --intent "Deploy a CIS-hardened RHEL 9 nginx web server with
                  centralized logging and node_exporter monitoring" \
        --mock

    # Full pipeline with validation
    python3 nl_infra_config.py \
        --intent "Configure NTP with chrony, CIS-hardened SSH, and
                  automatic audit rule deployment on all production servers" \
        --output-dir /tmp/nl_generated

    # Auto-deploy via platform API after validation
    python3 nl_infra_config.py \
        --intent "..." \
        --auto-deploy

Requirements:
    pip3 install pyyaml
"""

import argparse, json, logging, subprocess, sys
from pathlib import Path

sys.path.insert(0, "../../ch04-llm-playbook-generation/scripts")
from llm_provider import get_provider

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

NL_CONFIG_PROMPT = """
You are an expert Ansible automation architect specializing in enterprise Linux.
Convert a natural language infrastructure intent into a production-ready playbook.

Standards to apply:
- CIS RHEL 9 Level 1 baseline where applicable
- Fully qualified collection names (FQCN) for all modules
- pre_tasks for validation, post_tasks for verification
- Meaningful task names with [CATEGORY] prefix convention
- block/rescue for error handling on critical tasks
- Tags on all tasks matching: [category, specific_task]
- Idempotent task design throughout

Return exactly this JSON (no markdown, no preamble):
{
  "playbook_yaml": "<complete valid YAML playbook string>",
  "inventory_group": "<recommended Ansible group name>",
  "required_collections": ["ansible.posix", "community.general"],
  "required_roles": [],
  "estimated_runtime_minutes": <integer>,
  "summary": "One sentence: what this playbook accomplishes",
  "prerequisites": [
    "Prerequisite 1",
    "Prerequisite 2"
  ],
  "security_notes": [
    "Security consideration 1"
  ]
}
"""

MOCK_PLAYBOOK = '''---
- name: "[MOCK] CIS-Hardened NGINX Web Server Deployment"
  hosts: web_servers
  become: true
  gather_facts: true

  pre_tasks:
    - name: Verify target is RHEL/Rocky 8 or 9
      ansible.builtin.assert:
        that:
          - ansible_os_family == "RedHat"
          - ansible_distribution_major_version | int >= 8
        fail_msg: "Requires RHEL/Rocky 8+. Found: {{ ansible_distribution }} {{ ansible_distribution_version }}"
      tags: [validate, always]

  tasks:
    - name: "[PACKAGES] Install nginx and monitoring tools"
      ansible.builtin.dnf:
        name:
          - nginx
          - node_exporter
          - filebeat
        state: present
      tags: [packages, nginx]

    - name: "[SECURITY] Deploy CIS-hardened nginx configuration"
      ansible.builtin.template:
        src:   nginx.conf.j2
        dest:  /etc/nginx/nginx.conf
        owner: root
        group: root
        mode:  "0644"
        validate: nginx -t -c %s
      notify: reload nginx
      tags: [security, nginx, cis]

    - name: "[SERVICE] Enable and start nginx"
      ansible.builtin.service:
        name:    nginx
        state:   started
        enabled: true
      tags: [service, nginx]

    - name: "[FIREWALL] Open HTTP and HTTPS ports"
      ansible.posix.firewalld:
        service:   "{{ item }}"
        permanent: true
        state:     enabled
        immediate: true
      loop: [http, https]
      tags: [firewall, nginx]

  post_tasks:
    - name: "[VERIFY] Confirm nginx is serving requests"
      ansible.builtin.uri:
        url:         http://localhost
        status_code: 200
      retries: 3
      delay:   5
      tags: [verify, nginx]

  handlers:
    - name: reload nginx
      ansible.builtin.service:
        name:  nginx
        state: reloaded
'''


def generate_from_intent(intent:      str,
                         output_dir:  str  = "/tmp/nl_generated",
                         auto_deploy: bool = False,
                         mock:        bool = False) -> dict:
    """
    Generate infrastructure configuration from natural language intent.

    Pipeline stages:
      1. LLM generates playbook YAML from intent description
      2. YAML syntax validation via ansible-playbook --syntax-check
      3. ansible-lint quality and best-practice check
      4. AI security review using Chapter 4 review_playbook.py
      5. (Optional) Auto-deploy via platform API (Chapter 13)

    Args:
        intent:      Natural language description of desired infrastructure state
        output_dir:  Directory to write generated playbook
        auto_deploy: If True, trigger dry-run deploy via platform API after validation
        mock:        If True, skip LLM call and use mock playbook (for lab)

    Returns:
        Result dict with playbook path, validation stages, and metadata
    """
    log.info(f"Generating from intent: {intent[:80]}...")

    output_path  = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    playbook_file = output_path / "generated_playbook.yml"

    result = {
        "intent":      intent,
        "generated_at": None,
        "playbook":    str(playbook_file),
        "stages":      {},
        "summary":     "",
        "prereqs":     [],
        "collections": [],
        "roles":       [],
        "runtime_min": 0,
        "security_notes": [],
    }

    # ── Stage 1: Generate playbook ────────────────────────────────────────
    if mock:
        log.info("[MOCK] Using mock playbook — skipping LLM generation")
        playbook_yaml = MOCK_PLAYBOOK
        result["summary"]     = "[MOCK] CIS-hardened nginx with node_exporter and Filebeat"
        result["prereqs"]     = ["RHEL/Rocky 8+ target hosts", "nginx repo available"]
        result["collections"] = ["ansible.posix"]
        result["runtime_min"] = 5
        result["stages"]["generate"] = "mock"
    else:
        provider = get_provider()
        response = provider.generate(
            NL_CONFIG_PROMPT,
            f"Infrastructure intent:\n{intent}",
            temperature=0.1, max_tokens=4096
        )
        raw = response.content.strip()
        if raw.startswith("```"): raw = raw.split("\n", 1)[1]
        if raw.endswith("```"):   raw = raw.rsplit("\n", 1)[0]

        generated = json.loads(raw.strip())
        playbook_yaml         = generated["playbook_yaml"]
        result["summary"]     = generated.get("summary", "")
        result["prereqs"]     = generated.get("prerequisites", [])
        result["collections"] = generated.get("required_collections", [])
        result["roles"]       = generated.get("required_roles", [])
        result["runtime_min"] = generated.get("estimated_runtime_minutes", 5)
        result["security_notes"] = generated.get("security_notes", [])
        result["stages"]["generate"] = "passed"

    from datetime import datetime, timezone
    result["generated_at"] = datetime.now(timezone.utc).isoformat()
    playbook_file.write_text(playbook_yaml)
    log.info(f"Playbook written: {playbook_file} ({len(playbook_yaml)} bytes)")

    if mock:
        log.info("[MOCK] Skipping validation stages in mock mode")
        return result

    # ── Stage 2: Syntax check ─────────────────────────────────────────────
    log.info("Stage 2: Syntax check...")
    syntax = subprocess.run(
        ["ansible-playbook", "--syntax-check", str(playbook_file),
         "-i", "inventory/"],
        capture_output=True, text=True
    )
    result["stages"]["syntax"] = "passed" if syntax.returncode == 0 else "failed"
    if syntax.returncode != 0:
        log.error(f"Syntax check failed:\n{syntax.stderr[:400]}")
        return result
    log.info("  Syntax check: PASSED")

    # ── Stage 3: ansible-lint ─────────────────────────────────────────────
    log.info("Stage 3: ansible-lint...")
    lint = subprocess.run(
        ["ansible-lint", "--profile", "production", str(playbook_file)],
        capture_output=True, text=True
    )
    result["stages"]["lint"] = "passed" if lint.returncode == 0 else "warnings"
    log.info(f"  ansible-lint: {result['stages']['lint'].upper()}")

    # ── Stage 4: AI security review ───────────────────────────────────────
    log.info("Stage 4: AI security review...")
    try:
        review_script = Path("../../ch04-llm-playbook-generation/scripts/review_playbook.py")
        if review_script.exists():
            review_proc = subprocess.run(
                ["python3", str(review_script),
                 "--playbook", str(playbook_file)],
                capture_output=True, text=True
            )
            review_passed = review_proc.returncode == 0
            result["stages"]["ai_review"] = "passed" if review_passed else "flagged"
        else:
            result["stages"]["ai_review"] = "skipped (review_playbook.py not found)"
    except Exception as e:
        result["stages"]["ai_review"] = f"error: {e}"
    log.info(f"  AI review: {result['stages']['ai_review'].upper()}")

    # ── Stage 5: Auto-deploy ──────────────────────────────────────────────
    if auto_deploy:
        all_passed = all(v in ("passed", "warnings", "mock")
                         for v in result["stages"].values())
        if all_passed:
            log.info("Stage 5: Triggering dry-run deployment via platform API...")
            try:
                import requests
                resp = requests.post(
                    "http://localhost:8080/api/v1/remediate",
                    json={
                        "hostname":  "staging",
                        "playbook":  str(playbook_file),
                        "dry_run":   True,
                    },
                    timeout=10
                )
                result["stages"]["deploy"] = (
                    "dry_run_triggered" if resp.ok else f"api_error_{resp.status_code}"
                )
            except Exception as e:
                result["stages"]["deploy"] = f"platform_unavailable: {e}"
        else:
            result["stages"]["deploy"] = "skipped: validation failures"
        log.info(f"  Deploy: {result['stages']['deploy']}")

    return result


def print_result(result: dict) -> None:
    print(f"\nNL Infrastructure Configuration Generator")
    print(f"{'='*55}")
    print(f"Intent   : {result['intent'][:70]}...")
    print(f"Summary  : {result['summary']}")
    print(f"Playbook : {result['playbook']}")
    print(f"Runtime  : ~{result['runtime_min']} minutes")
    print(f"\nValidation Stages:")
    for stage, status in result["stages"].items():
        icon = "✔" if "passed" in status or "mock" in status or "triggered" in status else "⚠"
        print(f"  {icon}  {stage}: {status}")
    if result["prereqs"]:
        print(f"\nPrerequisites:")
        for p in result["prereqs"]:
            print(f"  • {p}")
    if result["collections"]:
        print(f"\nRequired collections: {', '.join(result['collections'])}")
    if result["security_notes"]:
        print(f"\nSecurity notes:")
        for n in result["security_notes"]:
            print(f"  ⚠  {n}")


def main():
    parser = argparse.ArgumentParser(
        description="Natural language to infrastructure configuration pipeline"
    )
    parser.add_argument("--intent",     required=True,
                        help="Natural language description of desired infrastructure state")
    parser.add_argument("--output-dir", default="/tmp/nl_generated")
    parser.add_argument("--mock",       action="store_true", default=True,
                        help="Use mock playbook (no LLM required for lab)")
    parser.add_argument("--live",       action="store_true",
                        help="Use live LLM (overrides --mock)")
    parser.add_argument("--auto-deploy", action="store_true",
                        help="Trigger dry-run deploy via platform API after validation")
    parser.add_argument("--json",       action="store_true")
    args = parser.parse_args()

    mock   = not args.live
    result = generate_from_intent(
        intent=args.intent,
        output_dir=args.output_dir,
        auto_deploy=args.auto_deploy,
        mock=mock,
    )

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print_result(result)
        print(f"\nGenerated playbook: {result['playbook']}")


if __name__ == "__main__":
    main()
