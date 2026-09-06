#!/usr/bin/env python3
"""
generate_docs.py — Chapter 4, Listing 4-8
Generate README and runbook documentation from existing Ansible roles.

Author : Balaramakrishna Alti
GitHub : https://github.com/balaramaa/ansible-aiops-playbook

Usage:
    python3 generate_docs.py --role roles/linux_baseline
    python3 generate_docs.py --role roles/ssh_hardening --format runbook
    python3 generate_docs.py --role roles/compliance --format both
"""

import argparse, logging
from pathlib import Path
from llm_provider import get_provider

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

DOCS_SYSTEM_PROMPT = """
You are a technical writer specializing in infrastructure documentation.
Write clear, accurate documentation for operations teams.
Your documentation is concise but complete — operators can follow it without guessing.
Use Markdown format. Include code blocks for all commands and YAML examples.
"""


def read_role(role_path: str) -> dict[str, str]:
    """Read YAML files from an Ansible role directory."""
    role = Path(role_path)
    files = {}
    for subdir in ["tasks", "handlers", "defaults", "vars", "meta"]:
        subdir_path = role / subdir
        if subdir_path.exists():
            for yml_file in sorted(subdir_path.glob("*.yml")):
                key = f"{subdir}/{yml_file.name}"
                content = yml_file.read_text()
                files[key] = content[:2000]  # Limit for token budget
    return files


def generate_readme(role_path: str) -> str:
    """Generate a README.md for an Ansible role."""
    files = read_role(role_path)
    role_name = Path(role_path).name

    file_summary = "\n\n".join(
        f"### {name}\n```yaml\n{content}\n```"
        for name, content in files.items()
    )

    prompt = f"""Generate a README.md for the Ansible role "{role_name}".

Role files:
{file_summary}

Include these sections:
1. **Description** — what the role does and why it exists
2. **Requirements** — OS versions, Ansible version, required collections
3. **Role Variables** — Markdown table: Variable | Default | Description
4. **Dependencies** — other roles this role depends on
5. **Example Playbook** — complete, working example
6. **Tags** — list all tags and what they apply
7. **License** — MIT
8. **Author** — Balaramakrishna Alti, The Ansible AIOps Playbook (Apress)

Use standard Ansible Galaxy README format.
Output Markdown only."""

    provider = get_provider()
    log.info(f"Generating README.md for role: {role_name}")
    response = provider.generate(DOCS_SYSTEM_PROMPT, prompt, max_tokens=3000)
    return response.content


def generate_runbook(role_path: str) -> str:
    """Generate an operator runbook from an Ansible role."""
    files = read_role(role_path)
    role_name = Path(role_path).name
    tasks_content = files.get("tasks/main.yml", "")

    prompt = f"""Convert this Ansible role into a human-readable operator runbook.

Role: {role_name}
Tasks file:
```yaml
{tasks_content}
```

The runbook should include:
1. **Overview** — what this role does and when it should be run
2. **Prerequisites** — what must be true before running
3. **Pre-flight Checks** — commands to verify the environment is ready
4. **Execution** — the exact ansible-playbook command(s) to run
5. **Verification** — how to confirm the role applied correctly
6. **Rollback** — how to undo changes if something goes wrong
7. **Common Issues** — troubleshooting table: Symptom | Cause | Fix

Target audience: Linux administrators who may not know Ansible.
Avoid Ansible internals — explain in plain operational terms.
Output Markdown only."""

    provider = get_provider()
    log.info(f"Generating RUNBOOK.md for role: {role_name}")
    response = provider.generate(DOCS_SYSTEM_PROMPT, prompt, max_tokens=3000)
    return response.content


def main():
    parser = argparse.ArgumentParser(
        description="Generate README and runbook docs from Ansible roles"
    )
    parser.add_argument("--role", required=True, help="Path to Ansible role directory")
    parser.add_argument("--format", choices=["readme", "runbook", "both"],
                        default="both", help="Document type to generate (default: both)")
    args = parser.parse_args()

    role_path = Path(args.role)
    if not role_path.exists():
        print(f"Role not found: {args.role}"); exit(1)

    generated = []

    if args.format in ("readme", "both"):
        readme = generate_readme(args.role)
        out = role_path / "README.md"
        out.write_text(readme)
        generated.append(str(out))
        log.info(f"✔ README written: {out}")

    if args.format in ("runbook", "both"):
        runbook = generate_runbook(args.role)
        out = role_path / "RUNBOOK.md"
        out.write_text(runbook)
        generated.append(str(out))
        log.info(f"✔ Runbook written: {out}")

    print("\nGenerated documentation:")
    for f in generated:
        print(f"  {f}")


if __name__ == "__main__":
    main()
