terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

# Firewall rules
resource "google_compute_firewall" "app_fw" {
  name    = "test-deploy-${var.deployment_id}-fw"
  network = "default"

  allow {
    protocol = "tcp"
    ports    = ["22", "80", "443", "3000", "8000"]
  }

  source_ranges = ["0.0.0.0/0"]
  target_tags   = ["test-deploy-${var.deployment_id}"]
}

# Compute Instance
resource "google_compute_instance" "app" {
  name         = "test-deploy-${var.deployment_id}"
  machine_type = var.instance_type
  zone         = "${var.region}-a"

  boot_disk {
    initialize_params {
      image = "ubuntu-os-cloud/ubuntu-2204-lts"
    }
  }

  network_interface {
    network = "default"
    access_config {
      // Ephemeral public IP
    }
  }

  metadata = {
    ssh-keys = "ubuntu:ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQCcQWMA1vWKJHqF70XrbqpqUgLXUIut6OrfQ+l1khBORhrzpeI5mMv5b5p+rpcRC+9bU9OPLEYjitO81ELBR5nKd0/Cotd3BqJVStwscH+a9hc8kjqBWiEZ84QppDQ5SiTmW5I7d2mhzswTgzk7uQMMM6mtP8c4wBB6jzk6WQSm4ybnea64SdiMLELyGpwsCIk3youEgL5xY4R1/Hk1XUWswupNw6xHKUf2i/ptQFQFgAHcMq3QGnC3ljzKpuPpbJmhAZZ4tbGDKNG/a8LSH9swH36ddlpxO4+tB6E8JnG2DQYn1sWYkj5BjsHPvX4gHPLawZrX5md2uQ9oSiLOVGvR deploy-key"
  }

  metadata_startup_script = <<-EOF
    #!/bin/bash
    apt-get update
    apt-get install -y python3-pip
    # Allow passwordless sudo for ubuntu user
    echo 'ubuntu ALL=(ALL) NOPASSWD:ALL' >> /etc/sudoers
  EOF

  tags = ["deploy-${var.deployment_id}"]

  labels = {
    deployment_id = var.deployment_id
  }
}
