# =============================================================================
# outputs.tf — The Ansible AIOps Playbook (Apress)
# Chapter 1: AWS Lab Environment Outputs
# =============================================================================

output "control_node_ip" {
  description = "Public IP of the Ansible control node"
  value       = aws_instance.control.public_ip
}

output "control_node_ssh" {
  description = "SSH command to connect to the control node"
  value       = "ssh -i scripts/${var.project_name}-key.pem rocky@${aws_instance.control.public_ip}"
}

output "managed_node_ips" {
  description = "Public IPs of all managed nodes"
  value       = aws_instance.managed[*].public_ip
}

output "managed_node_ssh_commands" {
  description = "SSH commands to connect to each managed node"
  value = [
    for i, ip in aws_instance.managed[*].public_ip :
    "ssh -i scripts/${var.project_name}-key.pem rocky@${ip}   # node0${i + 1}"
  ]
}

output "ansible_inventory_path" {
  description = "Path to the auto-generated Ansible inventory file"
  value       = "${path.module}/../scripts/inventory/hosts"
}

output "validate_lab_command" {
  description = "Command to validate the lab from the control node"
  value       = "cd /opt/ansible-aiops-playbook && ./chapters/ch01-lab-setup/scripts/validate_lab.sh"
}

output "estimated_hourly_cost_usd" {
  description = "Estimated hourly cost in USD (approximate)"
  value       = "~$0.19/hr (1x t3.large + 3x t3.medium in us-east-1)"
}
