#!/usr/bin/env bash
# setup_observability.sh — Chapter 2, Listing 2-16
# Complete observability foundation setup for a managed node
#
# Author : Balaramakrishna Alti
# GitHub : https://github.com/balaramaa/ansible-aiops-playbook
# Usage: sudo ./setup_observability.sh
set -euo pipefail

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; BOLD='\033[1m'; NC='\033[0m'
step() { echo -e "\n${BOLD}▶ $*${NC}"; }
ok()   { echo -e "  ${GREEN}✔${NC}  $*"; }
warn() { echo -e "  ${YELLOW}⚠${NC}  $*"; }
fail() { echo -e "  ${RED}✗${NC}  $*"; exit 1; }

[[ $EUID -ne 0 ]] && fail "Run as root: sudo $0"

step "1. Install observability tools"
dnf install -y -q bpftrace bcc-tools audit && ok "Tools installed"

step "2. Enable and configure auditd"
systemctl enable --now auditd && ok "auditd enabled"
tee /etc/audit/rules.d/99-cis.rules > /dev/null << 'EOF'
-w /etc/passwd -p wa -k identity
-w /etc/shadow -p wa -k identity
-w /etc/sudoers -p wa -k privilege_escalation
-w /etc/ssh/sshd_config -p wa -k ssh_config
-a always,exit -F arch=b64 -S setuid -k privilege_escalation
EOF
augenrules --load && ok "CIS audit rules loaded"

step "3. Apply SSH hardening"
cp /etc/ssh/sshd_config /etc/ssh/sshd_config.bak.$(date +%Y%m%d) 2>/dev/null || true
tee /etc/ssh/sshd_config.d/99-hardening.conf > /dev/null << 'EOF'
PermitRootLogin no
PermitEmptyPasswords no
MaxAuthTries 3
ClientAliveInterval 300
ClientAliveCountMax 0
X11Forwarding no
LogLevel VERBOSE
EOF
sshd -t && systemctl reload sshd && ok "SSH hardened"

step "4. Configure compliance check timer"
tee /etc/systemd/system/compliance-check.service > /dev/null << 'EOF'
[Unit]
Description=Compliance Check
[Service]
Type=oneshot
ExecStart=/usr/bin/bash -c "aureport --summary > /tmp/audit_report_$(date +%Y%m%d).txt 2>&1"
EOF
tee /etc/systemd/system/compliance-check.timer > /dev/null << 'EOF'
[Unit]
Description=Daily Compliance Check
[Timer]
OnCalendar=daily
RandomizedDelaySec=1800
Persistent=true
[Install]
WantedBy=timers.target
EOF
systemctl daemon-reload && systemctl enable --now compliance-check.timer && ok "Timer enabled"

step "5. Verify"
systemctl is-active auditd &>/dev/null && ok "auditd: running" || warn "auditd: NOT running"
systemctl is-active sshd  &>/dev/null && ok "sshd: running"   || warn "sshd: NOT running"
bpftrace -e 'BEGIN { printf("eBPF OK\n"); exit(); }' 2>/dev/null && ok "eBPF: working" || warn "eBPF: check kernel version"

echo -e "\n${BOLD}✔  Observability setup complete on $(hostname -s)${NC}"
