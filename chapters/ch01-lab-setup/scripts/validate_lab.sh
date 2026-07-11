#!/usr/bin/env bash
# =============================================================================
# validate_lab.sh — The Ansible AIOps Playbook (Apress)
# Chapter 1: Lab Environment Validation
#
# Author : Balaramakrishna Alti
# GitHub : https://github.com/balaramaa/ansible-aiops-playbook
#
# Validates that the control node and all managed nodes are correctly
# configured for the exercises in this book.
#
# Usage:
#   ./validate_lab.sh                        # Uses default inventory path
#   ./validate_lab.sh -i /path/to/inventory  # Custom inventory path
# =============================================================================

set -euo pipefail

# ── colour helpers ────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; BOLD='\033[1m'; NC='\033[0m'

pass()  { echo -e "  ${GREEN}✔${NC}  $*"; }
fail()  { echo -e "  ${RED}✗${NC}  $*"; FAILURES=$((FAILURES + 1)); }
warn()  { echo -e "  ${YELLOW}⚠${NC}  $*"; }
info()  { echo -e "  ${BLUE}ℹ${NC}  $*"; }
header(){ echo -e "\n${BOLD}${BLUE}▶ $*${NC}"; }

FAILURES=0
INVENTORY="${INVENTORY:-./inventory/hosts}"

# ── parse arguments ───────────────────────────────────────────────────────────
while getopts "i:h" opt; do
  case $opt in
    i) INVENTORY="$OPTARG" ;;
    h) echo "Usage: $0 [-i inventory_path]"; exit 0 ;;
    *) echo "Unknown option"; exit 1 ;;
  esac
done

echo -e "\n${BOLD}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}║  The Ansible AIOps Playbook — Lab Environment Validator      ║${NC}"
echo -e "${BOLD}║  Chapter 1: The Intelligent Infrastructure Imperative        ║${NC}"
echo -e "${BOLD}╚══════════════════════════════════════════════════════════════╝${NC}"

# ── 1. Operating System ───────────────────────────────────────────────────────
header "1. Operating System"
OS_ID=$(grep "^ID=" /etc/os-release | cut -d= -f2 | tr -d '"')
OS_VER=$(grep "^VERSION_ID=" /etc/os-release | cut -d= -f2 | tr -d '"')

if [[ "$OS_ID" =~ ^(rhel|rocky|almalinux|centos)$ ]]; then
  pass "OS: $OS_ID $OS_VER (supported)"
else
  warn "OS: $OS_ID $OS_VER — exercises tested on RHEL/Rocky Linux 9"
fi

MAJOR_VER="${OS_VER%%.*}"
if [[ "$MAJOR_VER" == "9" ]]; then
  pass "OS major version: 9 ✓"
else
  warn "OS major version: $MAJOR_VER — recommend version 9 for full compatibility"
fi

# ── 2. System Resources ───────────────────────────────────────────────────────
header "2. System Resources"
TOTAL_RAM_KB=$(grep MemTotal /proc/meminfo | awk '{print $2}')
TOTAL_RAM_GB=$(( TOTAL_RAM_KB / 1024 / 1024 ))
CPU_COUNT=$(nproc)
FREE_DISK_GB=$(df -BG / | tail -1 | awk '{print $4}' | tr -d 'G')

[[ $TOTAL_RAM_GB -ge 8 ]]  && pass "RAM: ${TOTAL_RAM_GB} GB (minimum 8 GB required)" \
                            || fail "RAM: ${TOTAL_RAM_GB} GB — minimum 8 GB required for control node"
[[ $CPU_COUNT -ge 4 ]]     && pass "CPUs: ${CPU_COUNT} (minimum 4 recommended)" \
                            || warn "CPUs: ${CPU_COUNT} — 4+ recommended for control node"
[[ $FREE_DISK_GB -ge 50 ]] && pass "Free disk: ${FREE_DISK_GB} GB (minimum 50 GB recommended)" \
                            || warn "Free disk: ${FREE_DISK_GB} GB — recommend at least 50 GB"

# ── 3. Python ─────────────────────────────────────────────────────────────────
header "3. Python"
if command -v python3 &>/dev/null; then
  PY_VER=$(python3 --version 2>&1 | awk '{print $2}')
  PY_MAJOR=$(echo "$PY_VER" | cut -d. -f1)
  PY_MINOR=$(echo "$PY_VER" | cut -d. -f2)
  pass "python3: $PY_VER found"
  [[ $PY_MAJOR -eq 3 && $PY_MINOR -ge 11 ]] \
    && pass "Python version ≥ 3.11 ✓" \
    || warn "Python $PY_VER — recommend 3.11+ for all AI/LLM features"
else
  fail "python3 not found — install with: sudo dnf install python3"
fi

if command -v pip3 &>/dev/null; then
  pass "pip3: $(pip3 --version | awk '{print $2}') found"
else
  fail "pip3 not found — install with: sudo dnf install python3-pip"
fi

# ── 4. Ansible ────────────────────────────────────────────────────────────────
header "4. Ansible"
if command -v ansible &>/dev/null; then
  ANS_VER=$(ansible --version | head -1 | awk '{print $NF}' | tr -d ']')
  pass "ansible: $ANS_VER found"
  ANS_MINOR=$(echo "$ANS_VER" | cut -d. -f2)
  [[ $ANS_MINOR -ge 15 ]] \
    && pass "ansible-core version ≥ 2.15 ✓" \
    || warn "ansible-core $ANS_VER — recommend 2.15+ for Event-Driven Ansible features"
else
  fail "ansible not found — install: sudo dnf install ansible-core"
fi

if command -v ansible-playbook &>/dev/null; then
  pass "ansible-playbook: found"
else
  fail "ansible-playbook not found"
fi

if command -v ansible-galaxy &>/dev/null; then
  pass "ansible-galaxy: found"
else
  fail "ansible-galaxy not found"
fi

# ── 5. Git ────────────────────────────────────────────────────────────────────
header "5. Git"
if command -v git &>/dev/null; then
  pass "git: $(git --version | awk '{print $3}') found"
  # check if repo is cloned
  if git rev-parse --git-dir &>/dev/null; then
    REMOTE=$(git remote get-url origin 2>/dev/null || echo "none")
    pass "Git repository detected — remote: $REMOTE"
  else
    warn "Not inside a git repository — clone the book repo first:"
    info "  git clone https://github.com/balaramaa/ansible-aiops-playbook.git"
  fi
else
  fail "git not found — install: sudo dnf install git"
fi

# ── 6. Container Runtime ──────────────────────────────────────────────────────
header "6. Container Runtime"
if command -v podman &>/dev/null; then
  pass "podman: $(podman --version | awk '{print $3}') found (preferred on RHEL/Rocky)"
elif command -v docker &>/dev/null; then
  pass "docker: $(docker --version | awk '{print $3}' | tr -d ',') found"
else
  warn "Neither podman nor docker found — required for Chapter 10 CI/CD exercises"
  info "  Install: sudo dnf install podman"
fi

# ── 7. Managed Node Connectivity ─────────────────────────────────────────────
header "7. Managed Node Connectivity (Ansible Ping)"
if [[ -f "$INVENTORY" ]]; then
  info "Using inventory: $INVENTORY"
  if ansible all -i "$INVENTORY" -m ping --timeout=10 2>&1 | grep -q "SUCCESS"; then
    REACHABLE=$(ansible all -i "$INVENTORY" -m ping --timeout=10 2>/dev/null \
      | grep -c "SUCCESS" || true)
    pass "Managed nodes reachable: $REACHABLE host(s) responded to ping"
  else
    fail "One or more managed nodes did not respond — check SSH keys and network"
    info "  Troubleshooting: ansible all -i $INVENTORY -m ping -vvv"
  fi
else
  warn "Inventory file not found at: $INVENTORY"
  info "  Create inventory/hosts or specify with: ./validate_lab.sh -i /path/to/inventory"
  info "  See appendices/appendix-a-lab-setup/ for inventory templates"
fi

# ── 8. Python Packages (AI/LLM) ───────────────────────────────────────────────
header "8. Python Packages for AI/LLM Chapters"
check_pkg() {
  python3 -c "import $1" 2>/dev/null \
    && pass "Python package '$1' installed" \
    || warn "Python package '$1' not yet installed (required from Chapter 4)"
}
check_pkg openai
check_pkg anthropic
check_pkg requests
check_pkg yaml

# ── 9. Ollama (Optional Local LLM) ───────────────────────────────────────────
header "9. Ollama — Local LLM (Optional)"
if command -v ollama &>/dev/null; then
  pass "ollama: found"
  if ollama list 2>/dev/null | grep -q "llama"; then
    pass "llama model pulled and ready"
  else
    warn "Ollama installed but no model pulled yet"
    info "  Pull a model: ollama pull llama3"
  fi
else
  info "ollama not installed — optional for air-gapped LLM use (Chapters 4+)"
  info "  Install: curl -fsSL https://ollama.com/install.sh | sh"
fi

# ── Summary ───────────────────────────────────────────────────────────────────
echo -e "\n${BOLD}╔══════════════════════════════════════════════════════════════╗${NC}"
if [[ $FAILURES -eq 0 ]]; then
  echo -e "${BOLD}║  ${GREEN}✔  All required checks passed — lab is ready!${NC}${BOLD}              ║${NC}"
else
  echo -e "${BOLD}║  ${RED}✗  $FAILURES check(s) failed — review output above${NC}${BOLD}               ║${NC}"
fi
echo -e "${BOLD}╚══════════════════════════════════════════════════════════════╝${NC}"
echo -e "\nBook repository: ${BLUE}https://github.com/balaramaa/ansible-aiops-playbook${NC}\n"

exit $FAILURES
