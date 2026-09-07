#!/usr/bin/env bash
# audit_ssh_keys.sh — Chapter 2, Listing 2-13
# SSH authorized_keys audit — outputs JSON for AI analytics pipeline
#
# Author : Balaramakrishna Alti
# GitHub : https://github.com/balaramaa/ansible-aiops-playbook
set -euo pipefail

readonly REPORT_FILE="/var/log/ssh_key_audit_$(date +%Y%m%d).json"

{
    printf '{"hostname":"%s","audit_time":"%s","authorized_keys":[\n' \
        "$(hostname -f)" "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    first=true
    while IFS= read -r -d "" auth_file; do
        user=$(stat -c "%U" "${auth_file}" 2>/dev/null || echo "unknown")
        key_count=$(grep -vc "^#\|^$" "${auth_file}" 2>/dev/null || echo 0)
        perms=$(stat -c "%a" "${auth_file}" 2>/dev/null || echo "unknown")
        perm_ok="true"; [[ "${perms}" != "600" && "${perms}" != "644" ]] && perm_ok="false"
        [[ "${first}" == "true" ]] || printf ','
        first=false
        printf '{"file":"%s","user":"%s","key_count":%s,"permissions":"%s","permissions_ok":%s}' \
            "${auth_file}" "${user}" "${key_count}" "${perms}" "${perm_ok}"
    done < <(find /home /root -name "authorized_keys" -print0 2>/dev/null)
    printf ']}\n'
} | tee "${REPORT_FILE}"
echo "[INFO] Report: ${REPORT_FILE}" >&2
