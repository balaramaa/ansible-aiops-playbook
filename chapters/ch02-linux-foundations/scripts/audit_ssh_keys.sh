#!/usr/bin/env bash
# audit_ssh_keys.sh — Chapter 2, Listing 2-13
# SSH authorized_keys audit for fleet environments
# Outputs JSON for ingestion by AI analytics pipeline (Chapter 11)
#
# Author : Balaramakrishna Alti
# GitHub : https://github.com/balaramaa/ansible-aiops-playbook
#
# Usage (single node):
#   sudo ./audit_ssh_keys.sh
#
# Usage (fleet via Ansible):
#   ansible all -i inventory/hosts -m script \
#     -a "chapters/ch02-linux-foundations/scripts/audit_ssh_keys.sh" \
#     --become

set -euo pipefail

readonly REPORT_FILE="/var/log/ssh_key_audit_$(date +%Y%m%d).json"
readonly AUDIT_TIME="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

# Start JSON output
{
    printf '{\n'
    printf '  "hostname": "%s",\n' "$(hostname -f)"
    printf '  "audit_time": "%s",\n' "${AUDIT_TIME}"
    printf '  "authorized_keys_files": [\n'

    first=true
    while IFS= read -r -d "" auth_file; do
        user=$(stat -c "%U" "${auth_file}" 2>/dev/null || echo "unknown")
        uid=$(id -u "${user}" 2>/dev/null || echo "-1")

        # Count non-comment, non-empty lines
        key_count=$(grep -vc "^#\|^$" "${auth_file}" 2>/dev/null || echo 0)

        # Check file permissions
        perms=$(stat -c "%a" "${auth_file}" 2>/dev/null || echo "unknown")

        # Flag overly permissive files
        perm_ok="true"
        [[ "${perms}" != "600" && "${perms}" != "644" ]] && perm_ok="false"

        [[ "${first}" == "true" ]] || printf ',\n'
        first=false

        printf '    {\n'
        printf '      "file": "%s",\n' "${auth_file}"
        printf '      "user": "%s",\n' "${user}"
        printf '      "uid": %s,\n' "${uid}"
        printf '      "key_count": %s,\n' "${key_count}"
        printf '      "permissions": "%s",\n' "${perms}"
        printf '      "permissions_ok": %s\n' "${perm_ok}"
        printf '    }'
    done < <(find /home /root /etc -name "authorized_keys" -print0 2>/dev/null)

    printf '\n  ],\n'
    printf '  "root_auth_keys_exists": %s\n' \
        "$([[ -f /root/.ssh/authorized_keys ]] && echo 'true' || echo 'false')"
    printf '}\n'
} | tee "${REPORT_FILE}"

echo "[INFO] Audit report written to: ${REPORT_FILE}" >&2
