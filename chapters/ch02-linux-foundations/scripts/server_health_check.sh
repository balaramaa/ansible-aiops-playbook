#!/usr/bin/env bash
# server_health_check.sh — Chapter 2, Listing 2-2 & 2-4
# Collect health metrics and output JSON for AI analytics pipeline
#
# Author : Balaramakrishna Alti
# GitHub : https://github.com/balaramaa/ansible-aiops-playbook
set -euo pipefail

readonly THRESHOLD_CPU=90
readonly THRESHOLD_MEM=85
readonly THRESHOLD_DISK=80
VERBOSE="${VERBOSE:-false}"
TMPFILE=$(mktemp /tmp/health_check.XXXXXX)
cleanup() { rm -f "${TMPFILE}"; }
trap cleanup EXIT

log_verbose() { [[ "${VERBOSE}" == "true" ]] && echo "[DEBUG] $*" >&2 || true; }

get_cpu_usage()     { top -bn1 | grep "Cpu(s)" | awk '{print int(100 - $8)}'; }
get_mem_usage()     { free | grep Mem | awk '{print int($3/$2 * 100)}'; }
get_disk_usage()    { df / | tail -1 | awk '{print $5}' | tr -d '%'; }
get_load_average()  { uptime | awk -F'[a-z]:' '{print $2}' | awk -F',' '{print $1}' | tr -d ' '; }
get_failed_services() { systemctl --failed --no-legend 2>/dev/null | grep -c "failed" || echo "0"; }

main() {
    local cpu_pct mem_pct disk_pct load_avg failed_svcs
    cpu_pct=$(get_cpu_usage)
    mem_pct=$(get_mem_usage)
    disk_pct=$(get_disk_usage)
    load_avg=$(get_load_average)
    failed_svcs=$(get_failed_services)

    local status="healthy"
    [[ ${cpu_pct}  -ge ${THRESHOLD_CPU}  ]] && status="warning"
    [[ ${mem_pct}  -ge ${THRESHOLD_MEM}  ]] && status="warning"
    [[ ${disk_pct} -ge ${THRESHOLD_DISK} ]] && status="warning"
    [[ ${failed_svcs} -gt 0              ]] && status="critical"

    cat << EOF
{
  "hostname": "$(hostname -s)",
  "fqdn": "$(hostname -f)",
  "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "status": "${status}",
  "metrics": {
    "cpu_pct": ${cpu_pct},
    "mem_pct": ${mem_pct},
    "disk_pct": ${disk_pct},
    "load_avg_1m": "${load_avg}",
    "failed_services": ${failed_svcs}
  }
}
EOF
}
main "$@"
