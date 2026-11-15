output "vpc_id" {
  description = "ID de la VPC creada"
  value       = aws_vpc.this.id
}

output "vpc_cidr_block" {
  description = "Bloque CIDR de la VPC"
  value       = aws_vpc.this.cidr_block
}

output "public_subnet_id" {
  description = "ID de la subred pública"
  value       = aws_subnet.public.id
}

output "private_subnet_id" {
  description = "ID de la subred privada"
  value       = aws_subnet.private.id
}

output "public_route_table_id" {
  description = "ID de la tabla de ruteo pública"
  value       = aws_route_table.public.id
}

output "private_route_table_id" {
  description = "ID de la tabla de ruteo privada"
  value       = aws_route_table.private.id
}
