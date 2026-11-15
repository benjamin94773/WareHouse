output "instance_id" {
  description = "ID de la instancia EC2"
  value       = aws_instance.this.id
}

output "public_ip" {
  description = "Dirección IP pública de la instancia EC2"
  value       = aws_instance.this.public_ip
}

output "private_ip" {
  description = "Dirección IP privada de la instancia EC2"
  value       = aws_instance.this.private_ip
}
