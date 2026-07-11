#!/usr/bin/env bash
# =============================================================================
# setup_managed_nodes.sh — The Ansible AIOps Playbook (Apress)
# Chapter 1: Managed Node Preparation
#
# Author : Balaramakrishna Alti
# GitHub : https://github.com/balaramaa/ansible-aiops-playbook
#
# Run this script ON EACH managed node (not the control node) to prepare it
# for Ansible management. Run as root or with sudo.
#
# Usage:
#   sudo ./setup_managed_nodes.sh --control-ip 192.168.1.10
# =============================================================================

set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; BOLD='\033[1m'; NC='\033[0m'

step() { echo -e "\n${BOLD}${BLUE}▶ $*${NC}"; }
ok()   { echo -e "  ${GREEN}✔${NC}  $*"; }
warn() { echo -e "  ${YELLOW}⚠${NC}  $*"; }
die()  { echo -e "  ${RED}✗  ERROR: $*${NC}"; exit 1; }

CONTROL_IP=""
for arg in "$@"; do
  [[ "$arg" == "--control-ip" ]] && { shift; CONTROL_IP="$1"; }
done

[[ $EUID -ne 0 ]] && die "Run as root: sudo $0"

HOSTNAME_SHORT=$(hostname -s)

echo -e "\n${BOLD}Preparing managed node: ${HOSTNAME_SHORT}${NC}"

step "1. Create ansible service account"
if ! id ansible &>/dev/null; then
  useradd -m -s /bin/bash -c "Ansible Service Account" ansible
  ok "User 'ansible' created"
else
  ok "User 'ansible' already exists"
fi

step "2. Configure passwordless sudo for ansible"
cat > /etc/sudoers.d/ansible << 'EOF'
# Ansible AIOps Playbook — managed node sudoers
ansible ALL=(ALL) NOPASSWD: ALL
EOF
chmod 440 /etc/sudoers.d/ansible
ok "Sudoers entry written for ansible user"

step "3. SSH authorized_keys setup"
ANSIBLE_SSH_DIR="/home/ansible/.ssh"
mkdir -p "$ANSIBLE_SSH_DIR"
chmod 700 "$ANSIBLE_SSH_DIR"
touch "${ANSIBLE_SSH_DIR}/authorized_keys"
chmod 600 "${ANSIBLE_SSH_DIR}/authorized_keys"
chown -R ansible:ansible "$ANSIBLE_SSH_DIR"

if [[ -n "$CONTROL_IP" ]]; then
  warn "Paste the control node's public key below and press Ctrl+D when done:"
  warn "  (Or run: ssh-copy-id -i ~/.ssh/id_ed25519.pub ansible@$(hostname -I | awk '{print $1}'))"
  warn "  from the control node to skip this step."
  cat >> "${ANSIBLE_SSH_DIR}/authorized_keys"
  ok "Public key added to authorized_keys"
else
  warn "No --control-ip provided. Add the control node public key manually:"
  warn "  cat /root/.ssh/id_ed25519.pub | ssh root@$(hostname -I | awk '{print $1}') \\"
  warn "  'cat >> /home/ansible/.ssh/authorized_keys'"
fi

step "4. Install Python 3 (required by Ansible)"
dnf install -y -q python3 python3-pip && ok "Python3 installed: $(python3 --version)"

step "5. Configure SSH daemon"
# Harden SSH while keeping key-based auth working
cp /etc/ssh/sshd_config /etc/ssh/sshd_config.bak
cat >> /etc/ssh/sshd_config << 'EOF'

# Ansible AIOps Playbook — managed node SSH settings
PermitRootLogin no
PasswordAuthentication no
PubkeyAuthentication yes
AuthorizedKeysFile .ssh/authorized_keys
MaxAuthTries 3
EOF
systemctl reload sshd && ok "SSH daemon reconfigured and reloaded"

step "6. Configure firewall"
if systemctl is-active --quiet firewalld; then
  firewall-cmd --permanent --add-service=ssh &>/dev/null
  firewall-cmd --reload &>/dev/null
  ok "Firewall: SSH service permitted"
else
  warn "firewalld not running — skipping firewall configuration"
fi

step "7. Set SELinux to enforcing (recommended for book exercises)"
if command -v getenforce &>/dev/null; then
  SELINUX_STATE=$(getenforce)
  if [[ "$SELINUX_STATE" == "Enforcing" ]]; then
    ok "SELinux: already Enforcing"
  else
    warn "SELinux: currently $SELINUX_STATE — setting to Enforcing in /etc/selinux/config"
    sed -i 's/^SELINUX=.*/SELINUX=enforcing/' /etc/selinux/config
    warn "SELinux change will take effect after reboot"
  fi
fi

step "8. Install required packages"
dnf install -y -q \
  openssh-server \
  sudo \
  curl \
  tar \
  && ok "Required packages installed"

# ── Summary ───────────────────────────────────────────────────────────────────
NODE_IP=$(hostname -I | awk '{print $1}')
echo -e "\n${BOLD}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}║  ${GREEN}✔  Managed node ${HOSTNAME_SHORT} is ready${NC}${BOLD}                          ║${NC}"
echo -e "${BOLD}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "From your control node, test connectivity:"
echo -e "  ${BLUE}ansible -i '${NODE_IP},' all -u ansible -m ping${NC}"
echo ""
echo -e "Add this node to your inventory (${BLUE}/root/book/inventory/hosts${NC}):"
echo -e "  ${BLUE}${HOSTNAME_SHORT} ansible_host=${NODE_IP} ansible_user=ansible${NC}"
echo ""
