output "cluster_id" {
  description = "ID del cluster ECS"
  value       = aws_ecs_cluster.this.id
}

output "cluster_name" {
  description = "Nombre del cluster ECS"
  value       = aws_ecs_cluster.this.name
}

output "cluster_arn" {
  description = "ARN del cluster ECS"
  value       = aws_ecs_cluster.this.arn
}
