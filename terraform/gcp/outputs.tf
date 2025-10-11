output "instance_id" {
  description = "Instance ID"
  value       = google_compute_instance.app.id
}

output "public_ip" {
  description = "Public IP address"
  value       = google_compute_instance.app.network_interface[0].access_config[0].nat_ip
}

output "private_ip" {
  description = "Private IP address"
  value       = google_compute_instance.app.network_interface[0].network_ip
}