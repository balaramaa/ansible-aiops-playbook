#!/usr/bin/env bash
# =============================================================================
# setup_control_node.sh — The Ansible AIOps Playbook (Apress)
# Chapter 1: Control Node Bootstrap
#
# Author : Balaramakrishna Alti
# GitHub : https://github.com/balaramaa/ansible-aiops-playbook
#
# Bootstraps a RHEL 9 / Rocky Linux 9 control node with all tools required
# for the exercises in this book. Run as root or with sudo.
#
# Usage:
#   sudo ./setup_control_node.sh
#   sudo ./setup_control_node.sh --skip-ollama   # Skip local LLM install
# =============================================================================

set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; BOLD='\033[1m'; NC='\033[0m'

step()  { echo -e "\n${BOLD}${BLUE}▶ $*${NC}"; }
ok()    { echo -e "  ${GREEN}✔${NC}  $*"; }
warn()  { echo -e "  ${YELLOW}⚠${NC}  $*"; }
die()   { echo -e "  ${RED}✗  ERROR: $*${NC}"; exit 1; }

SKIP_OLLAMA=false
for arg in "$@"; do [[ "$arg" == "--skip-ollama" ]] && SKIP_OLLAMA=true; done

[[ $EUID -ne 0 ]] && die "This script must be run as root: sudo $0"

# ── detect OS ─────────────────────────────────────────────────────────────────
OS_ID=$(grep "^ID=" /etc/os-release | cut -d= -f2 | tr -d '"')
[[ "$OS_ID" =~ ^(rhel|rocky|almalinux)$ ]] \
  || die "Unsupported OS: $OS_ID. This script supports RHEL/Rocky/AlmaLinux 9."

step "1. System Update"
dnf update -y -q && ok "System packages updated"

step "2. EPEL and Development Tools"
dnf install -y -q epel-release && ok "EPEL repository enabled"
dnf groupinstall -y -q "Development Tools" && ok "Development tools installed"
dnf install -y -q \
  git curl wget unzip tar \
  python3 python3-pip python3-devel \
  sshpass openssh-clients \
  vim-enhanced jq tree \
  && ok "Core utilities installed"

step "3. Ansible"
dnf install -y -q ansible-core && ok "ansible-core installed: $(ansible --version | head -1)"

# Install useful Ansible collections
ansible-galaxy collection install \
  ansible.posix \
  community.general \
  community.crypto \
  redhat.rhel_system_roles \
  2>/dev/null && ok "Core Ansible collections installed"

step "4. Python Packages for AI/LLM Chapters"
pip3 install -q --upgrade pip
pip3 install -q \
  openai \
  anthropic \
  requests \
  pyyaml \
  jinja2 \
  paramiko \
  boto3 \
  molecule \
  molecule-plugins[docker] \
  ansible-lint \
  && ok "Python AI/LLM packages installed"

step "5. Container Runtime (Podman)"
dnf install -y -q podman podman-compose && ok "Podman installed: $(podman --version)"

step "6. Terraform (for AWS lab exercises)"
# HashiCorp official repo
cat > /etc/yum.repos.d/hashicorp.repo << 'EOF'
[hashicorp]
name=HashiCorp Stable - $basearch
baseurl=https://rpm.releases.hashicorp.com/RHEL/$releasever/$basearch/stable
enabled=1
gpgcheck=1
gpgkey=https://rpm.releases.hashicorp.com/gpg
EOF
dnf install -y -q terraform && ok "Terraform installed: $(terraform version | head -1)"

step "7. SSH Key Generation"
if [[ ! -f /root/.ssh/id_ed25519 ]]; then
  ssh-keygen -t ed25519 -N "" -f /root/.ssh/id_ed25519 -C "ansible-aiops-lab" \
    && ok "SSH ed25519 key generated: /root/.ssh/id_ed25519.pub"
else
  ok "SSH key already exists: /root/.ssh/id_ed25519.pub"
fi

step "8. Ansible Configuration"
mkdir -p /etc/ansible
cat > /etc/ansible/ansible.cfg << 'EOF'
[defaults]
inventory           = ./inventory/hosts
remote_user         = ansible
private_key_file    = ~/.ssh/id_ed25519
host_key_checking   = False
retry_files_enabled = False
stdout_callback     = yaml
collections_path    = ~/.ansible/collections:/usr/share/ansible/collections
roles_path          = ./roles:~/.ansible/roles:/usr/share/ansible/roles

[privilege_escalation]
become      = True
become_method = sudo
become_user = root

[ssh_connection]
pipelining  = True
forks       = 20
EOF
ok "Ansible configuration written to /etc/ansible/ansible.cfg"

step "9. Book Repository"
REPO_DIR="/opt/ansible-aiops-playbook"
if [[ ! -d "$REPO_DIR" ]]; then
  git clone https://github.com/balaramaa/ansible-aiops-playbook.git "$REPO_DIR" \
    && ok "Book repository cloned to $REPO_DIR"
else
  cd "$REPO_DIR" && git pull -q && ok "Book repository updated at $REPO_DIR"
fi
ln -sf "$REPO_DIR" /root/book 2>/dev/null || true
ok "Shortcut created: /root/book → $REPO_DIR"

step "10. Ollama — Local LLM"
if $SKIP_OLLAMA; then
  warn "Ollama installation skipped (--skip-ollama flag)"
else
  if ! command -v ollama &>/dev/null; then
    curl -fsSL https://ollama.com/install.sh | sh && ok "Ollama installed"
  else
    ok "Ollama already installed: $(ollama --version 2>/dev/null || echo 'version unknown')"
  fi
  # Pull a lightweight model for initial testing
  ollama pull llama3 2>/dev/null && ok "llama3 model pulled" \
    || warn "Could not pull llama3 — run 'ollama pull llama3' manually"
fi

# ── Summary ───────────────────────────────────────────────────────────────────
echo -e "\n${BOLD}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}║  ${GREEN}✔  Control node setup complete!${NC}${BOLD}                              ║${NC}"
echo -e "${BOLD}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "Next steps:"
echo -e "  1. Copy your SSH public key to managed nodes:"
echo -e "     ${BLUE}ssh-copy-id -i ~/.ssh/id_ed25519.pub ansible@<node-ip>${NC}"
echo -e "  2. Set up your inventory file:"
echo -e "     ${BLUE}cp /root/book/appendices/appendix-a-lab-setup/inventory.example /root/book/inventory/hosts${NC}"
echo -e "  3. Validate the full lab:"
echo -e "     ${BLUE}cd /root/book && ./chapters/ch01-lab-setup/scripts/validate_lab.sh${NC}"
echo ""
