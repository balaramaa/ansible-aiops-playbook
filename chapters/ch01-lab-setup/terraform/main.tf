# =============================================================================
# main.tf — The Ansible AIOps Playbook (Apress)
# Chapter 1: AWS Lab Environment
#
# Author : Balaramakrishna Alti
# GitHub : https://github.com/balaramaa/ansible-aiops-playbook
#
# Provisions:
#   - 1 VPC with public subnet
#   - 1 Control node  (t3.large  — 2 vCPU, 8 GB RAM)
#   - 3 Managed nodes (t3.medium — 2 vCPU, 4 GB RAM)
#   - Security group allowing SSH and internal traffic
#   - Auto-generated Ansible inventory file
#
# Estimated cost: ~$4.50/day when running, $0 when stopped.
#
# Usage:
#   terraform init
#   terraform plan
#   terraform apply
#   terraform destroy   # when done — stops billing
# =============================================================================

terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    local = {
      source  = "hashicorp/local"
      version = "~> 2.4"
    }
    tls = {
      source  = "hashicorp/tls"
      version = "~> 4.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

# ── SSH Key Pair ──────────────────────────────────────────────────────────────
resource "tls_private_key" "lab_key" {
  algorithm = "ED25519"
}

resource "aws_key_pair" "lab_key" {
  key_name   = "${var.project_name}-key"
  public_key = tls_private_key.lab_key.public_key_openssh
}

resource "local_file" "private_key" {
  content         = tls_private_key.lab_key.private_key_openssh
  filename        = "${path.module}/../scripts/${var.project_name}-key.pem"
  file_permission = "0600"
}

# ── VPC & Networking ─────────────────────────────────────────────────────────
resource "aws_vpc" "lab" {
  cidr_block           = var.vpc_cidr
  enable_dns_hostnames = true
  enable_dns_support   = true
  tags = { Name = "${var.project_name}-vpc", Project = var.project_name }
}

resource "aws_internet_gateway" "lab" {
  vpc_id = aws_vpc.lab.id
  tags   = { Name = "${var.project_name}-igw", Project = var.project_name }
}

resource "aws_subnet" "public" {
  vpc_id                  = aws_vpc.lab.id
  cidr_block              = var.public_subnet_cidr
  availability_zone       = "${var.aws_region}a"
  map_public_ip_on_launch = true
  tags = { Name = "${var.project_name}-public-subnet", Project = var.project_name }
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.lab.id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.lab.id
  }
  tags = { Name = "${var.project_name}-rt", Project = var.project_name }
}

resource "aws_route_table_association" "public" {
  subnet_id      = aws_subnet.public.id
  route_table_id = aws_route_table.public.id
}

# ── Security Group ────────────────────────────────────────────────────────────
resource "aws_security_group" "lab" {
  name        = "${var.project_name}-sg"
  description = "Ansible AIOps Playbook lab security group"
  vpc_id      = aws_vpc.lab.id

  # SSH from your IP only — update var.allowed_ssh_cidr in variables.tf
  ingress {
    description = "SSH from allowed CIDR"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = [var.allowed_ssh_cidr]
  }

  # All traffic within the lab VPC
  ingress {
    description = "All internal traffic"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = [var.vpc_cidr]
  }

  # Prometheus/Grafana for Chapter 11 exercises
  ingress {
    description = "Prometheus"
    from_port   = 9090
    to_port     = 9090
    protocol    = "tcp"
    cidr_blocks = [var.allowed_ssh_cidr]
  }

  ingress {
    description = "Grafana"
    from_port   = 3000
    to_port     = 3000
    protocol    = "tcp"
    cidr_blocks = [var.allowed_ssh_cidr]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "${var.project_name}-sg", Project = var.project_name }
}

# ── AMI: Latest Rocky Linux 9 ────────────────────────────────────────────────
data "aws_ami" "rocky9" {
  most_recent = true
  owners      = ["792107900699"] # Rocky Linux official AWS account

  filter {
    name   = "name"
    values = ["Rocky-9-EC2-Base-9.*.x86_64*"]
  }

  filter {
    name   = "architecture"
    values = ["x86_64"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

# ── Control Node ─────────────────────────────────────────────────────────────
resource "aws_instance" "control" {
  ami                    = data.aws_ami.rocky9.id
  instance_type          = var.control_node_instance_type
  subnet_id              = aws_subnet.public.id
  vpc_security_group_ids = [aws_security_group.lab.id]
  key_name               = aws_key_pair.lab_key.key_name

  root_block_device {
    volume_size = 50
    volume_type = "gp3"
  }

  user_data = templatefile("${path.module}/userdata_control.sh.tpl", {
    project_name = var.project_name
  })

  tags = {
    Name    = "${var.project_name}-control"
    Role    = "control"
    Project = var.project_name
    Chapter = "ch01"
  }
}

# ── Managed Nodes ─────────────────────────────────────────────────────────────
resource "aws_instance" "managed" {
  count                  = var.managed_node_count
  ami                    = data.aws_ami.rocky9.id
  instance_type          = var.managed_node_instance_type
  subnet_id              = aws_subnet.public.id
  vpc_security_group_ids = [aws_security_group.lab.id]
  key_name               = aws_key_pair.lab_key.key_name

  root_block_device {
    volume_size = 20
    volume_type = "gp3"
  }

  user_data = templatefile("${path.module}/userdata_managed.sh.tpl", {
    node_number = count.index + 1
  })

  tags = {
    Name    = "${var.project_name}-node0${count.index + 1}"
    Role    = "managed"
    Project = var.project_name
    Chapter = "ch01"
    NodeNum = tostring(count.index + 1)
  }
}

# ── Auto-generated Ansible Inventory ─────────────────────────────────────────
resource "local_file" "ansible_inventory" {
  filename = "${path.module}/../scripts/inventory/hosts"
  content = templatefile("${path.module}/ansible_inventory.tpl", {
    control_ip   = aws_instance.control.public_ip
    managed_ips  = aws_instance.managed[*].public_ip
    managed_names = [for i in range(var.managed_node_count) : "node0${i + 1}"]
    key_file     = "${path.module}/../scripts/${var.project_name}-key.pem"
    project_name = var.project_name
  })
  file_permission = "0644"
}
