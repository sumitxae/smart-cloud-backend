variable "deployment_id" {
  description = "Unique deployment identifier"
  type        = string
}

variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "region" {
  description = "GCP region"
  type        = string
  default     = "us-central1"
}

variable "instance_type" {
  description = "GCP machine type"
  type        = string
  default     = "e2-micro"
}
