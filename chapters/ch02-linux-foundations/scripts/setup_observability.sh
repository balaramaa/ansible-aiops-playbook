#!/usr/bin/env bash
# setup_observability.sh — Chapter 2, Listing 2-16
# Complete observability foundation setup for a managed node
# Run this on each managed node as root to complete the Chapter 2 lab exercise
#
# Author : Balaramakrishna Alti
# GitHub : https://github.com/balaramaa/ansible-aiops-playbook
#
# Usage:
#   sudo ./setup_observability.sh
#
# In Chapter 3, this entire script becomes an Ansible role.

set -euo pipefail

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'
BOLD='\033[1m'; NC='\033[0m'

step() { echo -e "\n${BOLD}▶ $*${NC}"; }
ok()   { echo -e "  ${GREEN}✔${NC}  $*"; }
warn() { echo -e "  ${YELLOW}⚠${NC}  $*"; }
fail() { echo -e "  ${RED}✗${NC}  $*"; exit 1; }

[[ $EUID -ne 0 ]] && fail "Run as root: sudo $0"

echo -e "\n${BOLD}Chapter 2 Lab: Observability Foundation Setup${NC}"
echo -e "${BOLD}Node: $(hostname -f)${NC}\n"

# ── Step 1: Install tools ─────────────────────────────────────────────────────
step "1. Install observability tools"
dnf install -y -q bpftrace bcc-tools audit && ok "bpftrace, BCC tools, auditd installed"

# ── Step 2: Enable auditd ─────────────────────────────────────────────────────
step "2. Enable and configure auditd"
systemctl enable --now auditd && ok "auditd enabled and started"

# Deploy CIS audit rules
cat > /etc/audit/rules.d/99-cis.rules << 'RULES_EOF'
-w /etc/passwd -p wa -k identity
-w /etc/shadow -p wa -k identity
-w /etc/sudoers -p wa -k privilege_escalation
-w /etc/sudoers.d/ -p wa -k privilege_escalation
-w /etc/ssh/sshd_config -p wa -k ssh_config
-a always,exit -F arch=b64 -S setuid -k privilege_escalation
-a always,exit -F arch=b64 -S setgid -k privilege_escalation
-w /sbin/insmod -p x -k modules
-w /sbin/rmmod -p x -k modules
RULES_EOF

augenrules --load && ok "CIS audit rules loaded"

# ── Step 3: SSH hardening ─────────────────────────────────────────────────────
step "3. Apply SSH hardening (CIS Level 1)"

# Backup existing config
cp /etc/ssh/sshd_config /etc/ssh/sshd_config.bak.$(date +%Y%m%d) 2>/dev/null || true

cat > /etc/ssh/sshd_config.d/99-hardening.conf << 'SSH_EOF'
PermitRootLogin no
PermitEmptyPasswords no
MaxAuthTries 3
LoginGraceTime 60
ClientAliveInterval 300
ClientAliveCountMax 0
X11Forwarding no
AllowAgentForwarding no
LogLevel VERBOSE
SSH_EOF

# Test config before reloading
sshd -t && ok "SSH config syntax valid"
systemctl reload sshd && ok "SSH daemon reloaded with hardening config"

# ── Step 4: Systemd timer ────────────────────────────────────────────────────
step "4. Configure compliance check timer"

cat > /etc/systemd/system/compliance-check.service << 'SVC_EOF'
[Unit]
Description=Compliance Check
[Service]
Type=oneshot
ExecStart=/usr/bin/bash -c "aureport --summary > /tmp/audit_report_$(date +%Y%m%d).txt 2>&1"
SVC_EOF

cat > /etc/systemd/system/compliance-check.timer << 'TMR_EOF'
[Unit]
Description=Daily Compliance Check
[Timer]
OnCalendar=daily
RandomizedDelaySec=1800
Persistent=true
[Install]
WantedBy=timers.target
TMR_EOF

systemctl daemon-reload
systemctl enable --now compliance-check.timer && ok "Compliance check timer enabled"

# ── Step 5: Verify ───────────────────────────────────────────────────────────
step "5. Verification"

systemctl is-active auditd &>/dev/null \
    && ok "auditd: running" \
    || warn "auditd: NOT running"

systemctl is-active sshd &>/dev/null \
    && ok "sshd: running with hardened config" \
    || warn "sshd: NOT running"

systemctl is-enabled compliance-check.timer &>/dev/null \
    && ok "compliance-check.timer: enabled" \
    || warn "compliance-check.timer: NOT enabled"

bpftrace -e 'BEGIN { printf("eBPF OK\n"); exit(); }' 2>/dev/null \
    && ok "eBPF: kernel support confirmed" \
    || warn "eBPF: not available on this kernel"

echo -e "\n${BOLD}✔  Observability foundation complete on $(hostname -s)${NC}"
echo "   In Chapter 3, this setup will be automated across your entire fleet."
echo ""
