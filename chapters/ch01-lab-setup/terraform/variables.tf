# =============================================================================
# variables.tf — The Ansible AIOps Playbook (Apress)
# Chapter 1: AWS Lab Environment Variables
# =============================================================================

variable "aws_region" {
  description = "AWS region for the lab environment"
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Project name used as prefix for all resource names"
  type        = string
  default     = "ansible-aiops-lab"
}

variable "vpc_cidr" {
  description = "CIDR block for the lab VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "public_subnet_cidr" {
  description = "CIDR block for the public subnet"
  type        = string
  default     = "10.0.1.0/24"
}

variable "allowed_ssh_cidr" {
  description = "CIDR allowed to SSH into lab nodes. IMPORTANT: change to your IP."
  type        = string
  default     = "0.0.0.0/0"  # Restrict to your IP: "203.0.113.5/32"
}

variable "control_node_instance_type" {
  description = "EC2 instance type for the Ansible control node"
  type        = string
  default     = "t3.large"   # 2 vCPU, 8 GB RAM — minimum for control node
}

variable "managed_node_instance_type" {
  description = "EC2 instance type for managed nodes"
  type        = string
  default     = "t3.medium"  # 2 vCPU, 4 GB RAM
}

variable "managed_node_count" {
  description = "Number of managed nodes to create"
  type        = number
  default     = 3
  validation {
    condition     = var.managed_node_count >= 2 && var.managed_node_count <= 6
    error_message = "managed_node_count must be between 2 and 6."
  }
}
