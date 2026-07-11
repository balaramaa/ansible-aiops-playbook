# Appendix A — Lab Environment Setup
### Complete guide to setting up your learning environment

*The Ansible AIOps Playbook: Building Self-Healing Linux Systems at Scale*
https://github.com/balaramaa/ansible-aiops-playbook

---

## Overview

This appendix provides everything needed to build the lab environment used throughout
the book. Two options are available:

- **Option A: Local** — VirtualBox or KVM on your workstation
- **Option B: AWS** — Auto-provisioned with Terraform (~$4.50/day)

Full setup scripts are in `chapters/ch01-lab-setup/`.

---

## Inventory Example

```ini
# inventory/hosts — copy and update IPs for your lab
[control]
control ansible_host=192.168.1.10 ansible_user=ansible

[managed]
node01 ansible_host=192.168.1.11 ansible_user=ansible
node02 ansible_host=192.168.1.12 ansible_user=ansible
node03 ansible_host=192.168.1.13 ansible_user=ansible

[lab:children]
control
managed

[lab:vars]
ansible_python_interpreter=/usr/bin/python3
ansible_ssh_private_key_file=~/.ssh/id_ed25519
```

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `UNREACHABLE` on ping | Check SSH key: `ssh-copy-id ansible@<node-ip>` |
| Python not found | `sudo dnf install python3` on managed node |
| Permission denied (sudo) | Check `/etc/sudoers.d/ansible` on managed node |
| Ollama timeout | Model still loading — wait 30s and retry |
| OpenAI 401 error | Check `OPENAI_API_KEY` is exported in current shell |
