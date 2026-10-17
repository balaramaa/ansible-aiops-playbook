# The Ansible AIOps Playbook
### Building Self-Healing Linux Systems at Scale

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Ansible](https://img.shields.io/badge/Ansible-2.15%2B-red.svg)](https://docs.ansible.com)
[![Python](https://img.shields.io/badge/Python-3.11%2B-green.svg)](https://python.org)
[![RHEL](https://img.shields.io/badge/RHEL%2FRocky-8%20%7C%209-red.svg)](https://www.redhat.com)
![Visitor Count](https://visitor-badge.laobi.icu/badge?page_id=balaramaa.ansible-aiops-playbook)

> **Companion repository for the Apress book by Balaramakrishna Alti**
> Published by Springer Nature · ISBN applied
> [github.com/balaramaa/ansible-aiops-playbook](https://github.com/balaramaa/ansible-aiops-playbook)

---

## What Is This?

This repository contains **production-ready code** for building a complete AIOps platform on enterprise Linux — the exact automation framework used to manage 8,000+ RHEL servers at Moody's Corporation.

Every file in this repository was built for real production use, not as a demonstration. It covers:

- **CIS RHEL 9 hardening** (Level 1 and Level 2) with full compliance automation
- **Self-healing infrastructure** using Event-Driven Ansible and AI root cause analysis
- **Predictive patch management** with five-dimension CVE risk scoring
- **AI-powered security automation** including eBPF threat detection and SIEM integration
- **Hybrid cloud automation** across AWS EC2, VMware vSphere, and Nutanix AHV
- **Complete CI/CD pipeline** with Molecule testing, ansible-lint, and compliance gates
- **AIOps platform** with Redis event bus, AI decision engine, and REST API

---

## Quick Start (15 Minutes)

### Prerequisites

```bash
# Control node (RHEL/Rocky 9 or Ubuntu 22.04)
python3 --version   # 3.11+
ansible --version   # 2.15+

# Managed nodes
# RHEL 8 or 9 / Rocky Linux 8 or 9
# SSH access with sudo from control node
```

### Step 1: Clone and Install

```bash
git clone https://github.com/balaramaa/ansible-aiops-playbook.git
cd ansible-aiops-playbook

# Install Python dependencies
pip3 install ansible-core==2.15.* \
             openai anthropic requests pyyaml \
             molecule molecule-docker ansible-lint

# Install required Ansible collections
ansible-galaxy collection install -r requirements.yml
```

### Step 2: Configure Your Inventory

```bash
# Edit inventory/hosts.yml and add your servers
cat inventory/hosts.yml
```

```yaml
all:
  children:
    lab:
      hosts:
        node01:
          ansible_host: 192.168.1.11   # ← change to your server IP
        node02:
          ansible_host: 192.168.1.12
    production:
      hosts:
        # your production servers here
```

### Step 3: Set Up SSH Access

```bash
# Generate Ansible SSH key (skip if you have one)
ssh-keygen -t ed25519 -f ~/.ssh/ansible_key -N ""

# Copy to managed nodes
ssh-copy-id -i ~/.ssh/ansible_key root@192.168.1.11

# Test connectivity
ansible all -i inventory/ -m ping --private-key ~/.ssh/ansible_key
```

### Step 4: Apply Your First Baseline

```bash
# Dry run first — see what would change
ansible-playbook -i inventory/ site.yml \
  --limit lab --check --diff \
  --private-key ~/.ssh/ansible_key

# Apply the baseline
ansible-playbook -i inventory/ site.yml \
  --limit lab \
  --private-key ~/.ssh/ansible_key
```

That's it. Your servers now have NTP, SSH hardening, auditd rules, CIS sysctl parameters, and the Ansible service account configured.

---

## Repository Structure

```
ansible-aiops-playbook/
├── inventory/                    # Unified hybrid inventory
│   ├── hosts.yml                 # Static hosts (lab / edge)
│   ├── aws_ec2.yml               # AWS EC2 dynamic inventory
│   ├── vmware_inventory.yml      # VMware vSphere dynamic inventory
│   ├── satellite_inventory.yml   # Red Hat Satellite dynamic inventory
│   └── group_vars/               # Per-group variables
├── roles/                        # Shared roles (linked from chapters)
├── site.yml                      # Main entry point playbook
├── requirements.yml              # Collection dependencies
└── chapters/
    ├── ch01-lab-setup/           # Lab environment setup
    ├── ch02-linux-foundations/   # eBPF, systemd, SSH, auditd
    ├── ch03-ansible-architecture/# linux_baseline role, AAP integration
    ├── ch04-llm-playbook-generation/ # AI playbook generator + reviewer
    ├── ch05-compliance-governance/   # CIS RHEL 9 role (all 6 sections)
    ├── ch06-patch-management/    # CVE scoring + canary patching
    ├── ch07-self-healing/        # EDA rulebooks + remediation playbooks
    ├── ch08-security-automation/ # eBPF detection + SIEM + PAM
    ├── ch09-cloud-hybrid/        # AWS + VMware + Nutanix + cost governance
    ├── ch10-cicd-pipelines/      # Molecule + GitHub Actions + Jenkins
    ├── ch11-observability/       # Prometheus + Grafana + Loki + anomaly detection
    ├── ch12-migration/           # Discovery + AI assessment + phased migration
    ├── ch13-aiops-platform/      # Event bus + AI engine + REST API
    └── ch14-future/              # ReAct agent + NL config + governance
```

---

## Chapter-by-Chapter Usage Guide

### Chapter 2 — Linux Infrastructure Foundations

```bash
# Start eBPF privilege escalation monitoring
sudo bpftrace chapters/ch02-linux-foundations/ebpf/detect_privilege_escalation.bt

# Run server health check (outputs JSON)
bash chapters/ch02-linux-foundations/scripts/server_health_check.sh

# Audit SSH authorized keys across all managed nodes
ansible all -i inventory/ -m script \
  -a "chapters/ch02-linux-foundations/scripts/audit_ssh_keys.sh" \
  --become
```

### Chapter 3 — Ansible Architecture

```bash
# Apply linux_baseline role to lab nodes
ansible-playbook -i inventory/ site.yml --limit lab --tags baseline

# Trigger an AAP job template via REST API
export AAP_URL="https://aap.company.com"
export AAP_USERNAME="ansible-svc"
export AAP_PASSWORD="your-password"
export JOB_TEMPLATE_ID="42"
python3 chapters/ch03-ansible-architecture/scripts/trigger_aap_job.py
```

### Chapter 4 — AI-Assisted Playbook Generation

```bash
# Set your LLM provider (choose one)
export OPENAI_API_KEY="sk-..."          # OpenAI
export ANTHROPIC_API_KEY="sk-ant-..."  # Anthropic Claude
# Or run Ollama locally (no API key needed):
# ollama serve && ollama pull llama3

# Generate a playbook from a prompt file
python3 chapters/ch04-llm-playbook-generation/scripts/generate_playbook.py \
  --prompt chapters/ch04-llm-playbook-generation/prompts/ssh_hardening.txt \
  --output /tmp/generated_ssh_hardening.yml

# AI review of any existing playbook
python3 chapters/ch04-llm-playbook-generation/scripts/review_playbook.py \
  --playbook /tmp/generated_ssh_hardening.yml \
  --fail-on high
```

### Chapter 5 — CIS Compliance Automation

```bash
# Apply full CIS RHEL 9 Level 1 hardening
ansible-playbook -i inventory/ \
  chapters/ch05-compliance-governance/playbooks/compliance_check.yml \
  --limit lab \
  -e "min_compliance_score=90"

# Run compliance baseline collection
python3 chapters/ch05-compliance-governance/scripts/compliance_baseline.py \
  --hosts lab --inventory inventory/

# Classify compliance drift with AI risk scoring
python3 chapters/ch05-compliance-governance/scripts/drift_classifier.py \
  --host node01 --mock

# Generate SOX/PCI-DSS evidence package
python3 chapters/ch05-compliance-governance/scripts/generate_evidence.py \
  --host node01 --framework SOX --output /tmp/evidence/
```

### Chapter 6 — Predictive Patch Management

```bash
# Score CVEs by five-dimension risk model (mock mode)
python3 chapters/ch06-patch-management/scripts/cve_risk_scorer.py \
  --mock --cve CVE-2024-1234

# Find optimal patch maintenance windows
python3 chapters/ch06-patch-management/scripts/window_optimizer.py \
  --group prod_web --risk-tier medium --mock

# Run full patch orchestration pipeline (dry run)
python3 chapters/ch06-patch-management/scripts/patch_orchestrator.py \
  --group lab --mock --dry-run

# Execute canary patching playbook
ansible-playbook -i inventory/ \
  chapters/ch06-patch-management/playbooks/patch_canary.yml \
  --limit lab --check --diff
```

### Chapter 7 — Self-Healing Infrastructure

```bash
# Install Event-Driven Ansible
pip3 install ansible-rulebook ansible-runner
ansible-galaxy collection install ansible.eda

# Start the self-healing rulebook (stays running, listening for alerts)
ansible-rulebook \
  --rulebook chapters/ch07-self-healing/eda-rulebooks/self_healing.yml \
  --inventory inventory/ \
  --verbose &

# Simulate a memory pressure alert to test EDA
curl -s -X POST http://localhost:8000/endpoint \
  -H "Content-Type: application/json" \
  -d '{
    "alerts": [{
      "labels": {
        "alertname": "HighMemoryUsage",
        "instance":  "node01:9100",
        "severity":  "critical"
      },
      "status": "firing"
    }]
  }'

# Run AI root cause analysis (mock mode)
python3 chapters/ch07-self-healing/scripts/rca_engine.py \
  --host node01 --alert HighMemoryUsage --mock

# View MTTR metrics from audit log
python3 chapters/ch07-self-healing/scripts/mttr_analyzer.py
```

### Chapter 8 — Security Automation

```bash
# Start eBPF privilege escalation detector
sudo bpftrace \
  chapters/ch08-security-automation/ebpf-security/detect_privilege_escalation.bt \
  > /var/log/security_events.jsonl &

# Test AI security event classifier with a simulated threat
python3 chapters/ch08-security-automation/scripts/security_event_analyzer.py \
  --test-event privilege_escalation

# Run vulnerability scan and remediation plan (mock mode)
python3 chapters/ch08-security-automation/scripts/vuln_remediation.py \
  --mock --plan

# Run authentication discovery (read-only — makes no changes)
ansible-playbook -i inventory/ \
  chapters/ch08-security-automation/playbooks/auth_migration/phase1_discovery.yml \
  --limit lab \
  -e "migration_name=lab-discovery"
```

### Chapter 9 — Cloud and Hybrid Automation

```bash
# AWS: Audit EC2 tagging compliance (dry run, no changes)
export AWS_ACCESS_KEY_ID="..."
export AWS_SECRET_ACCESS_KEY="..."
ansible-playbook \
  chapters/ch09-cloud-hybrid/playbooks/aws/enforce_tagging.yml \
  -e "enforce_tagging=false aws_region=us-east-1"

# AI cloud cost analysis (mock mode — no AWS credentials needed)
python3 chapters/ch09-cloud-hybrid/scripts/cloud_cost_analyzer.py --mock

# Apply universal baseline to all environments
ansible-playbook -i inventory/ \
  chapters/ch09-cloud-hybrid/playbooks/cloud/universal_baseline.yml \
  --limit lab --check --diff
```

### Chapter 10 — CI/CD Pipeline

```bash
# Install Molecule for role testing
pip3 install molecule molecule-docker

# Run full Molecule test lifecycle for linux_baseline role
cd chapters/ch03-ansible-architecture
molecule test

# Run ansible-lint against all roles
cd /root/ansible-aiops-playbook
ansible-lint

# Install pre-commit hooks
pip3 install pre-commit
cp chapters/ch10-cicd-pipelines/.pre-commit-config.yaml .
pre-commit install
pre-commit run --all-files

# Copy GitHub Actions workflow to enable CI on your fork
mkdir -p .github/workflows
cp chapters/ch10-cicd-pipelines/.github/workflows/ansible-ci.yml \
   .github/workflows/
git add .github/ && git commit -m "Add CI/CD pipeline" && git push
```

### Chapter 11 — Observability

```bash
# Deploy Prometheus + Grafana + node_exporter + Promtail
ansible-playbook -i inventory/ \
  chapters/ch11-observability/playbooks/deploy_observability.yml \
  --limit lab

# Verify node_exporter custom Ansible metrics
curl -s http://node01:9100/metrics | grep "ansible_"

# Run AI anomaly detection (mock mode)
python3 chapters/ch11-observability/scripts/anomaly_detector.py \
  --metric node_cpu_seconds_total --mock

# Run capacity forecasting (mock mode)
python3 chapters/ch11-observability/scripts/anomaly_detector.py \
  --forecast --metric node_filesystem_avail_bytes --mock
```

### Chapter 12 — Large-Scale Migration

```bash
# Phase 1: Read-only discovery (makes NO changes to targets)
ansible-playbook -i inventory/ \
  chapters/ch12-migration/playbooks/migration/phase1_discovery.yml \
  --limit lab \
  -e "migration_name=lab-test"

# View discovery results
cat /tmp/migration_discovery/lab-test-$(date +%Y-%m-%d)/SUMMARY.json \
  | python3 -m json.tool

# Phase 2: AI readiness assessment (mock mode)
python3 chapters/ch12-migration/scripts/migration_assessor.py \
  --discovery-dir /tmp/migration_discovery/lab-test-$(date +%Y-%m-%d)/ \
  --mock

# Generate migration batch plan
python3 chapters/ch12-migration/scripts/migration_planner.py \
  --assessment /tmp/assessment_results.json \
  --batch-size 10 \
  --start-date $(date +%Y-%m-%d)
```

### Chapter 13 — AIOps Platform

```bash
# Install platform dependencies
pip3 install fastapi uvicorn[standard] redis pydantic

# Start the platform API
cd /root/ansible-aiops-playbook
uvicorn chapters/ch13-aiops-platform/scripts/platform_api:app \
  --host 0.0.0.0 --port 8080 &

# Verify platform is running
curl -s http://localhost:8080/health | python3 -m json.tool

# Publish a test event to the platform
curl -s -X POST http://localhost:8080/api/v1/events \
  -H "Content-Type: application/json" \
  -d '{
    "event_type": "alert",
    "hostname":   "node01",
    "severity":   "critical",
    "payload":    {"alert_name": "HighMemoryUsage", "value": 94.2},
    "source":     "prometheus",
    "environment": "lab"
  }'

# Run the AI decision engine (mock mode)
python3 chapters/ch13-aiops-platform/scripts/ai_decision_engine.py \
  --mock --test-event memory

# Compute platform-wide metrics
python3 chapters/ch13-aiops-platform/scripts/platform_metrics.py --days 30

# View API documentation (Swagger UI)
echo "Open http://localhost:8080/docs in your browser"
```

### Chapter 14 — Autonomous Future

```bash
# Run the infrastructure investigation agent (mock mode)
python3 chapters/ch14-future/scripts/infra_agent.py \
  --goal "Investigate high memory usage on node01" \
  --mock

# Generate a playbook from natural language (mock mode)
python3 chapters/ch14-future/scripts/nl_infra_config.py \
  --intent "Deploy a CIS-hardened nginx web server with centralized logging" \
  --mock

# Test the AI governance framework
python3 chapters/ch14-future/scripts/ai_governance.py --test

# Generate governance audit report
python3 chapters/ch14-future/scripts/ai_governance.py --report --days 30
```

---

## Environment Variables Reference

| Variable | Used By | Description |
|---|---|---|
| `OPENAI_API_KEY` | Ch 4, 5, 6, 7, 8, 11–14 | OpenAI API key |
| `ANTHROPIC_API_KEY` | Ch 4, 5, 6, 7, 8, 11–14 | Anthropic Claude API key |
| `OLLAMA_HOST` | Ch 4+ | Ollama local server URL (default: http://localhost:11434) |
| `AAP_URL` | Ch 3 | Ansible Automation Platform URL |
| `AAP_USERNAME` | Ch 3 | AAP service account username |
| `AAP_PASSWORD` | Ch 3 | AAP service account password |
| `TENABLE_ACCESS_KEY` | Ch 8 | Tenable.io access key |
| `TENABLE_SECRET_KEY` | Ch 8 | Tenable.io secret key |
| `SNOW_INSTANCE` | Ch 7, 8 | ServiceNow instance name |
| `SNOW_USER` | Ch 7, 8 | ServiceNow username |
| `SNOW_PASS` | Ch 7, 8 | ServiceNow password |
| `SLACK_WEBHOOK_URL` | Ch 7 | Slack incoming webhook URL |
| `REDIS_URL` | Ch 13 | Redis connection URL (default: redis://localhost:6379) |
| `VMWARE_HOST` | Ch 9 | vCenter hostname |
| `VMWARE_USER` | Ch 9 | vCenter username |
| `VMWARE_PASSWORD` | Ch 9 | vCenter password |
| `NUTANIX_HOST` | Ch 9 | Prism Central hostname |
| `NUTANIX_USER` | Ch 9 | Prism Central username |
| `NUTANIX_PASS` | Ch 9 | Prism Central password |

---

## LLM Provider Configuration

All AI features use the abstraction layer in `ch04-llm-playbook-generation/scripts/llm_provider.py`. It auto-detects which provider to use based on available environment variables.

```bash
# Option 1: OpenAI (GPT-4o)
export OPENAI_API_KEY="sk-..."
export LLM_PROVIDER="openai"      # optional, auto-detected

# Option 2: Anthropic Claude
export ANTHROPIC_API_KEY="sk-ant-..."
export LLM_PROVIDER="anthropic"   # optional, auto-detected

# Option 3: Ollama (free, runs locally, no API key)
ollama serve
ollama pull llama3
export LLM_PROVIDER="ollama"
export OLLAMA_MODEL="llama3"

# Test the provider
python3 chapters/ch04-llm-playbook-generation/scripts/llm_provider.py
```

---

## Mock Mode (No Infrastructure Required)

Every script that calls external APIs (Prometheus, Satellite, Tenable, Ansible, Redis) has a `--mock` flag for safe exploration without live infrastructure:

```bash
python3 chapters/ch06-patch-management/scripts/patch_orchestrator.py --mock
python3 chapters/ch07-self-healing/scripts/rca_engine.py --mock --host node01 --alert HighMemoryUsage
python3 chapters/ch08-security-automation/scripts/vuln_remediation.py --mock --plan
python3 chapters/ch09-cloud-hybrid/scripts/cloud_cost_analyzer.py --mock
python3 chapters/ch11-observability/scripts/anomaly_detector.py --mock
python3 chapters/ch12-migration/scripts/migration_assessor.py --discovery-dir /tmp/discovery/ --mock
python3 chapters/ch13-aiops-platform/scripts/ai_decision_engine.py --mock
python3 chapters/ch14-future/scripts/infra_agent.py --mock --goal "Test investigation"
```

---

## Requirements

### Control Node
| Package | Version | Purpose |
|---|---|---|
| ansible-core | ≥ 2.15 | Automation engine |
| Python | ≥ 3.11 | Scripts and AI layer |
| ansible-rulebook | ≥ 1.0 | Event-Driven Ansible (Ch 7, 13) |
| molecule | ≥ 6.0 | Role testing (Ch 10) |
| fastapi + uvicorn | ≥ 0.110 | Platform API (Ch 13) |
| redis-py | ≥ 5.0 | Event bus client (Ch 13) |

### Managed Nodes
| Requirement | Details |
|---|---|
| OS | RHEL / Rocky Linux 8 or 9 |
| Python | 3.9+ (for Ansible modules) |
| SSH access | Key-based, with sudo |
| Disk | ≥ 2 GB free on `/` |

### Optional Integrations
| Service | Chapters | Required For |
|---|---|---|
| OpenAI / Anthropic / Ollama | 4–14 | All AI features |
| Red Hat Satellite | 3, 6 | Patch management live mode |
| Prometheus + Grafana | 11 | Observability stack |
| AWS account | 9 | EC2 automation |
| VMware vCenter | 9 | vSphere automation |
| Nutanix Prism Central | 9 | AHV automation |
| Redis | 13 | AIOps event bus |
| ServiceNow | 7, 8 | ITSM integration |

---

## Testing

```bash
# Run Molecule tests for linux_baseline role
cd chapters/ch03-ansible-architecture
molecule test

# Run Molecule tests for CIS hardening role
cd chapters/ch05-compliance-governance
molecule test

# Lint all playbooks and roles
cd /root/ansible-aiops-playbook
ansible-lint

# Syntax check all playbooks
find . -name "*.yml" -path "*/playbooks/*" | \
  while read f; do
    ansible-playbook --syntax-check "$f" -i inventory/
  done
```

---

## Contributing

Contributions are welcome. Please:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/your-improvement`)
3. Run `ansible-lint` and `molecule test` before submitting
4. Open a pull request with a clear description

For questions or to share how you are using this repository, open a [GitHub Discussion](https://github.com/balaramaa/ansible-aiops-playbook/discussions).

---

## Citation

If you use this repository in your work, research, or organization, please cite:

```
Balaramakrishna Alti (2025).
The Ansible AIOps Playbook: Building Self-Healing Linux Systems at Scale.
Apress / Springer Nature.
https://github.com/balaramaa/ansible-aiops-playbook
```

---

## Author

**Balaramakrishna Alti**
Senior Infrastructure Automation Architect
Moody's Corporation · Charlotte, NC

- GitHub: [@balaramaa](https://github.com/balaramaa)
- Published: *Computer Fraud & Security*, Elsevier (2024)
- Published: *Contemporary Readings in Law and Social Justice* (2024)

---

## License

MIT License — see [LICENSE](LICENSE) for details.

The code in this repository is free to use, modify, and distribute.
Attribution is appreciated but not required for commercial use.
