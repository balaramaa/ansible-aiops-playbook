#!/usr/bin/env python3
"""
generate_playbook.py — Chapter 4, Listing 4-4
LLM-powered Ansible playbook and role generator.

Author : Balaramakrishna Alti
GitHub : https://github.com/balaramaa/ansible-aiops-playbook

Usage:
    python3 generate_playbook.py --task "Harden SSH on RHEL 9"
    python3 generate_playbook.py --task "Configure NTP" --provider ollama
    python3 generate_playbook.py --task-file prompts/ssh_hardening.txt
    python3 generate_playbook.py --task-file prompts/auditd_cis.txt --output ./generated

Requirements:
    pip3 install openai anthropic pyyaml requests
"""

import argparse, json, logging, sys, yaml
from pathlib import Path
from llm_provider import get_provider

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
log = logging.getLogger(__name__)

SYSTEM_PROMPT = """
You are an expert Ansible engineer with 15+ years of enterprise Linux experience.
You write production-grade Ansible playbooks and roles that:
- Use fully qualified collection names (ansible.builtin.*, ansible.posix.*)
- Have a descriptive name: on every task
- Are idempotent — safe to run multiple times without side effects
- Include appropriate handlers for service restarts (with notify:)
- Support --check mode (add check_mode: true where needed)
- Validate prerequisites with ansible.builtin.assert
- Handle errors gracefully with block/rescue where appropriate
- Follow CIS Benchmark security standards unless otherwise specified
- Use tags on all tasks

Target environment: RHEL 9 / Rocky Linux 9
Ansible version: 2.15+
Output: valid YAML only — no markdown code fences, no prose explanations.
"""


def clean_yaml_output(raw: str) -> str:
    """Remove markdown fences that LLMs sometimes add."""
    lines = raw.strip().splitlines()
    if lines and lines[0].strip().startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines)


def validate_yaml(content: str, label: str = "output") -> bool:
    """Validate that the LLM output is parseable YAML."""
    try:
        parsed = yaml.safe_load(content)
        if parsed is None:
            log.warning(f"YAML is valid but empty for {label}")
            return False
        log.info(f"✔ YAML validation passed: {label}")
        return True
    except yaml.YAMLError as e:
        log.error(f"✗ YAML validation FAILED for {label}: {e}")
        return False


def generate_role(task: str,
                  provider_name: str = None,
                  output_dir: str = "./generated") -> Path:
    """
    Generate a complete Ansible role from a task description.

    Args:
        task:          Natural language description of what the role should do
        provider_name: 'openai' | 'anthropic' | 'ollama' | None (auto)
        output_dir:    Directory to write the generated role

    Returns:
        Path to the generated role directory
    """
    provider = get_provider(provider_name)

    # Derive role name from task
    words = task.lower().split()[:5]
    role_name = "_".join(w for w in words if w.isalpha())
    if not role_name:
        role_name = "generated_role"

    log.info(f"Generating role: '{role_name}'")
    log.info(f"Task: {task[:80]}...")

    # ── tasks/main.yml ──────────────────────────────────────────────────────
    tasks_prompt = f"""Task: {task}

Generate ONLY the tasks/main.yml file for a complete Ansible role.
Include:
- ansible.builtin.assert to validate prerequisites (OS version, etc.)
- All tasks needed to accomplish the goal
- Proper notify: directives for handlers
- Tags on every task
- block/rescue for operations that might fail

Output valid YAML starting with ---"""

    log.info("Generating tasks/main.yml...")
    tasks_resp = provider.generate(SYSTEM_PROMPT, tasks_prompt)
    tasks_yaml = clean_yaml_output(tasks_resp.content)
    tasks_valid = validate_yaml(tasks_yaml, "tasks/main.yml")

    # ── defaults/main.yml ───────────────────────────────────────────────────
    defaults_prompt = f"""For an Ansible role that: {task}

Generate ONLY the defaults/main.yml file.
Include all variables referenced in tasks with sensible production defaults.
Add a comment above each variable explaining its purpose and valid values.
Output valid YAML starting with ---"""

    log.info("Generating defaults/main.yml...")
    defaults_resp = provider.generate(SYSTEM_PROMPT, defaults_prompt)
    defaults_yaml = clean_yaml_output(defaults_resp.content)
    validate_yaml(defaults_yaml, "defaults/main.yml")

    # ── handlers/main.yml ───────────────────────────────────────────────────
    handlers_prompt = f"""For an Ansible role that: {task}

Generate ONLY the handlers/main.yml file.
Include handlers for service restarts, reloads, and daemon-reload.
Use ansible.builtin.service and ansible.builtin.systemd modules.
Output valid YAML starting with ---"""

    log.info("Generating handlers/main.yml...")
    handlers_resp = provider.generate(SYSTEM_PROMPT, handlers_prompt)
    handlers_yaml = clean_yaml_output(handlers_resp.content)
    validate_yaml(handlers_yaml, "handlers/main.yml")

    # ── Write role to disk ──────────────────────────────────────────────────
    role_dir = Path(output_dir) / role_name
    for d in ["tasks","handlers","defaults","vars","templates","files","meta"]:
        (role_dir / d).mkdir(parents=True, exist_ok=True)

    (role_dir / "tasks"    / "main.yml").write_text(tasks_yaml)
    (role_dir / "defaults" / "main.yml").write_text(defaults_yaml)
    (role_dir / "handlers" / "main.yml").write_text(handlers_yaml)

    # ── Generation metadata ─────────────────────────────────────────────────
    total_tokens = (tasks_resp.output_tokens +
                    defaults_resp.output_tokens +
                    handlers_resp.output_tokens)
    metadata = {
        "generated_by": f"{provider.__class__.__name__}/{tasks_resp.model}",
        "task": task,
        "role_name": role_name,
        "yaml_valid": tasks_valid,
        "tokens_used": total_tokens,
        "files_generated": ["tasks/main.yml", "defaults/main.yml", "handlers/main.yml"],
        "WARNING": "Review ALL generated code before running in production. "
                   "LLMs can produce plausible-looking but incorrect Ansible. "
                   "Test with --check --diff first."
    }
    (role_dir / "GENERATED.json").write_text(json.dumps(metadata, indent=2))

    log.info(f"✔ Role written to: {role_dir}")
    log.info(f"  Total tokens: {total_tokens}")
    log.info(f"  YAML valid  : {tasks_valid}")
    return role_dir


def main():
    parser = argparse.ArgumentParser(
        description="LLM-powered Ansible role generator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 generate_playbook.py --task "Harden SSH on RHEL 9 per CIS Level 1"
  python3 generate_playbook.py --task-file prompts/ssh_hardening.txt --provider ollama
  python3 generate_playbook.py --task "Configure auditd" --output ~/ansible/roles
        """
    )
    parser.add_argument("--task", help="Task description (natural language)")
    parser.add_argument("--task-file", help="File containing task description")
    parser.add_argument("--provider", choices=["openai","anthropic","ollama"],
                        help="LLM provider (default: auto-detect from env vars)")
    parser.add_argument("--output", default="./generated",
                        help="Output directory for generated role (default: ./generated)")
    args = parser.parse_args()

    if args.task_file:
        task = Path(args.task_file).read_text().strip()
    elif args.task:
        task = args.task
    else:
        parser.error("Provide --task or --task-file")

    role_dir = generate_role(task, args.provider, args.output)

    print(f"\n{'='*60}")
    print(f"Generated role: {role_dir}")
    print(f"{'='*60}")
    print("\nNext steps:")
    print(f"  1. Review:  cat {role_dir}/tasks/main.yml")
    print(f"  2. Review:  cat {role_dir}/defaults/main.yml")
    print(f"  3. Review:  python3 review_playbook.py --playbook {role_dir}/tasks/main.yml")
    print(f"  4. Test:    ansible-playbook --check --diff -e 'role_path={role_dir}' test.yml")


if __name__ == "__main__":
    main()
