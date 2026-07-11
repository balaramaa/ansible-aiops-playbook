# The Ansible AIOps Playbook
## Building Self-Healing Linux Systems at Scale

**Author:** Balaramakrishna Alti  
**Publisher:** Apress / Springer Nature  
**ISBN:** (assigned at publication)

---

## About This Repository

This repository contains all source code, Ansible playbooks, Python scripts,
Terraform templates, and supplementary materials for the book
*The Ansible AIOps Playbook: Building Self-Healing Linux Systems at Scale*.

## Repository Structure
ansible-aiops-playbook/
├── chapters/
│   ├── ch01-lab-setup/          # Chapter 1: Lab environment & Terraform templates
│   ├── ch02-linux-foundations/  # Chapter 2: eBPF, systemd, SSH hardening
│   ├── ch03-ansible-architecture/  # Chapter 3: Roles, Collections, AAP
│   ├── ch04-llm-playbook-generation/  # Chapter 4: AI playbook generation
│   ├── ch05-compliance-governance/    # Chapter 5: Compliance automation
│   ├── ch06-patch-management/         # Chapter 6: Predictive patching
│   ├── ch07-self-healing/             # Chapter 7: EDA, self-healing
│   ├── ch08-security-automation/      # Chapter 8: Security hardening
│   ├── ch09-cloud-hybrid/             # Chapter 9: AWS, VMware, Nutanix
│   ├── ch10-cicd-pipelines/           # Chapter 10: CI/CD for infra
│   ├── ch11-observability/            # Chapter 11: Prometheus, Grafana, AI
│   ├── ch12-migration/                # Chapter 12: Migration patterns
│   ├── ch13-aiops-platform/           # Chapter 13: AIOps architecture
│   └── ch14-future/                   # Chapter 14: Agentic AI
├── appendices/                        # Reference material for all appendices
└── shared/                            # Reusable roles, modules, filters

## Lab Environment Requirements

- Control node: RHEL 9 or Rocky Linux 9 (4 vCPUs, 8 GB RAM)
- Managed nodes: Rocky Linux 9 × 3 (1 vCPU, 2 GB RAM each)
- Ansible Automation Platform 2.4+ or ansible-core 2.15+
- Python 3.11+

See `appendices/appendix-a-lab-setup/` for full setup instructions.

## License

MIT License — see [LICENSE](LICENSE) for details.
