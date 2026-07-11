# Chapter 1 — The Intelligent Infrastructure Imperative

Source code and lab setup materials for **Chapter 1** of  
*The Ansible AIOps Playbook: Building Self-Healing Linux Systems at Scale*  
**Author:** Balaramakrishna Alti | **Publisher:** Apress / Springer Nature

---

## Contents

```
ch01-lab-setup/
├── README.md                        # This file
├── scripts/
│   ├── validate_lab.sh              # Validates your full lab environment
│   ├── setup_control_node.sh        # Bootstraps the Ansible control node
│   ├── setup_managed_nodes.sh       # Prepares managed nodes for Ansible
│   └── test_llm_connectivity.py     # Tests OpenAI / Anthropic / Ollama APIs
└── terraform/
    ├── main.tf                      # AWS lab infrastructure (VPC, EC2, SG)
    ├── variables.tf                 # Input variables
    ├── outputs.tf                   # Outputs: IPs, SSH command
    └── ansible_inventory.tpl        # Auto-generated Ansible inventory template
```

---

## Quick Start

### Option A — Local Virtualization (VirtualBox / KVM)

1. Create one control node VM: RHEL 9 or Rocky Linux 9, 4 vCPUs, 8 GB RAM
2. Create three managed node VMs: Rocky Linux 9, 1 vCPU, 2 GB RAM each
3. Run the bootstrap scripts:

```bash
# On the control node
chmod +x scripts/setup_control_node.sh
sudo ./scripts/setup_control_node.sh

# Validate the full lab
chmod +x scripts/validate_lab.sh
./scripts/validate_lab.sh
```

### Option B — AWS (Estimated cost: under $5/day)

```bash
cd terraform/
terraform init
terraform plan
terraform apply
```

After `apply` completes, Terraform prints the SSH connection commands and
writes a ready-to-use Ansible inventory file to `../scripts/inventory/hosts`.

---

## LLM API Setup

Chapter 4 onwards requires at least one LLM provider. Test connectivity:

```bash
# Set your API keys (never commit these to git)
export OPENAI_API_KEY="sk-..."
export ANTHROPIC_API_KEY="sk-ant-..."

python3 scripts/test_llm_connectivity.py
```

Ollama (free, local, no API key) is supported as a fallback:

```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull llama3
python3 scripts/test_llm_connectivity.py --provider ollama
```

---

## References

- Book GitHub repository: https://github.com/balaramaa/ansible-aiops-playbook
- Appendix A (full lab setup guide): `../../appendices/appendix-a-lab-setup/`
- Ansible documentation: https://docs.ansible.com
- Red Hat Satellite documentation: https://access.redhat.com/documentation/satellite
