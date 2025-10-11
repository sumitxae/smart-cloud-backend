

# ===========================================
# FILE: terraform/aws/outputs.tf
# ===========================================
output "instance_id" {
  description = "EC2 instance ID"
  value       = aws_instance.app.id
}

output "public_ip" {
  description = "Public IP address"
  value       = aws_instance.app.public_ip
}

output "private_ip" {
  description = "Private IP address"
  value       = aws_instance.app.private_ip
}
