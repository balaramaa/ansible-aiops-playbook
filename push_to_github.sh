#!/usr/bin/env bash
# =============================================================================
# push_to_github.sh — The Ansible AIOps Playbook
# One-shot script to push the complete repository to GitHub
#
# Usage:
#   chmod +x push_to_github.sh
#   ./push_to_github.sh
# =============================================================================

set -euo pipefail

BOLD='\033[1m'; GREEN='\033[0;32m'; BLUE='\033[0;34m'; NC='\033[0m'

REPO_URL="https://github.com/balaramaa/ansible-aiops-playbook.git"
REPO_DIR="ansible-aiops-playbook"

echo -e "\n${BOLD}The Ansible AIOps Playbook — GitHub Repository Setup${NC}"
echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"

# ── Step 1: Clone the existing repo ──────────────────────────────────────────
echo -e "${BLUE}▶ Step 1: Clone existing repository${NC}"
if [ -d "$REPO_DIR" ]; then
  echo "  Directory '$REPO_DIR' already exists — pulling latest..."
  cd "$REPO_DIR" && git pull && cd ..
else
  git clone "$REPO_URL"
fi
echo -e "  ${GREEN}✔ Repository ready${NC}"

# ── Step 2: Copy all files from the zip into the repo ────────────────────────
echo -e "\n${BLUE}▶ Step 2: Copy repo files${NC}"
echo "  Extracting repo_files.zip into $REPO_DIR/ ..."
unzip -o repo_files.zip -d "$REPO_DIR/" > /dev/null
echo -e "  ${GREEN}✔ Files copied${NC}"

# ── Step 3: Stage all changes ────────────────────────────────────────────────
echo -e "\n${BLUE}▶ Step 3: Stage all changes${NC}"
cd "$REPO_DIR"
git add -A
STATUS=$(git status --short | wc -l)
echo -e "  ${GREEN}✔ $STATUS files staged${NC}"

# ── Step 4: Commit ───────────────────────────────────────────────────────────
echo -e "\n${BLUE}▶ Step 4: Commit${NC}"
git commit -m "Complete repository structure: all 14 chapters + appendices + shared components

- Root README.md with full book overview, badges, and quick start
- .gitignore covering Ansible, Python, Terraform, SSH keys, and secrets
- MIT LICENSE
- All 14 chapter folders with detailed READMEs and sub-folder structure
- All 5 appendix folders with READMEs (A: lab setup, B: Ansible reference,
  C: CIS mapping, D: prompt library, E: resources)
- Shared roles, modules, inventory-plugins, filters directories
- Chapter 1 complete: lab scripts, Terraform AWS templates, validation tools

Book: The Ansible AIOps Playbook (Apress / Springer Nature)
Author: Balaramakrishna Alti <balaramaa@gmail.com>"
echo -e "  ${GREEN}✔ Committed${NC}"

# ── Step 5: Push ─────────────────────────────────────────────────────────────
echo -e "\n${BLUE}▶ Step 5: Push to GitHub${NC}"
git push origin main
echo -e "  ${GREEN}✔ Pushed successfully${NC}"

# ── Done ─────────────────────────────────────────────────────────────────────
echo -e "\n${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BOLD}${GREEN}✔  Repository is live!${NC}"
echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "  View your repo: ${BLUE}https://github.com/balaramaa/ansible-aiops-playbook${NC}"
echo ""
