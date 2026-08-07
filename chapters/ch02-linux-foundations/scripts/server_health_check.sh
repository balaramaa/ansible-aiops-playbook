#!/usr/bin/env bash
# server_health_check.sh — Chapter 2, Listing 2-2 & 2-4
# Collect health metrics from managed nodes
# Outputs JSON for ingestion by Ansible or AI analytics pipeline (Chapter 11)
#
# Author : Balaramakrishna Alti
# GitHub : https://github.com/balaramaa/ansible-aiops-playbook
#
# Usage:
#   ./server_health_check.sh              # JSON output
#   VERBOSE=true ./server_health_check.sh # Verbose output
#   ansible all -i inventory/hosts -m script \
#     -a "chapters/ch02-linux-foundations/scripts/server_health_check.sh"

set -euo pipefail

# ── Configuration ────────────────────────────────────────────────────────────
readonly THRESHOLD_CPU=90
readonly THRESHOLD_MEM=85
readonly THRESHOLD_DISK=80
readonly LOG_FILE="/var/log/health_check.log"
VERBOSE="${VERBOSE:-false}"

# ── Cleanup ──────────────────────────────────────────────────────────────────
TMPFILE=$(mktemp /tmp/health_check.XXXXXX)
cleanup() { rm -f "${TMPFILE}"; }
trap cleanup EXIT

# ── Logging ──────────────────────────────────────────────────────────────────
log() {
    local level="$1"; shift
    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] [${level}] $*" | tee -a "${LOG_FILE}"
}

log_verbose() {
    [[ "${VERBOSE}" == "true" ]] && log "DEBUG" "$*" || true
}

# ── Metric collection ────────────────────────────────────────────────────────
get_cpu_usage() {
    # Get CPU usage as integer percentage (0-100)
    top -bn1 | grep "Cpu(s)" | awk '{print int(100 - $8)}'
}

get_mem_usage() {
    # Get memory usage percentage
    free | grep Mem | awk '{print int($3/$2 * 100)}'
}

get_disk_usage() {
    # Get root filesystem usage percentage
    df / | tail -1 | awk '{print $5}' | tr -d '%'
}

get_load_average() {
    # 1-minute load average
    uptime | awk -F'[a-z]:' '{print $2}' | awk -F',' '{print $1}' | tr -d ' '
}

get_failed_services() {
    # Count failed systemd services
    systemctl --failed --no-legend 2>/dev/null | grep -c "failed" || echo "0"
}

# ── Main ─────────────────────────────────────────────────────────────────────
main() {
    log_verbose "Health check starting on $(hostname -f)"

    local cpu_pct mem_pct disk_pct load_avg failed_svcs
    cpu_pct=$(get_cpu_usage)
    mem_pct=$(get_mem_usage)
    disk_pct=$(get_disk_usage)
    load_avg=$(get_load_average)
    failed_svcs=$(get_failed_services)

    # Determine overall health status
    local status="healthy"
    [[ ${cpu_pct}  -ge ${THRESHOLD_CPU}  ]] && status="warning"
    [[ ${mem_pct}  -ge ${THRESHOLD_MEM}  ]] && status="warning"
    [[ ${disk_pct} -ge ${THRESHOLD_DISK} ]] && status="warning"
    [[ ${failed_svcs} -gt 0              ]] && status="critical"

    log_verbose "CPU: ${cpu_pct}% | MEM: ${mem_pct}% | DISK: ${disk_pct}% | STATUS: ${status}"

    # Output structured JSON for Ansible register or AI pipeline ingestion
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
  },
  "thresholds": {
    "cpu": ${THRESHOLD_CPU},
    "mem": ${THRESHOLD_MEM},
    "disk": ${THRESHOLD_DISK}
  }
}
EOF
}

main "$@"
