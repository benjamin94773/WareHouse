output "bodegas_ips" {
  description = "Direcciones IP públicas y privadas de las bodegas creadas dinámicamente"
  value = {
    for name, instance in module.ec2_bodegas : name => {
      id         = instance.instance_id
      public_ip  = instance.public_ip
      private_ip = instance.private_ip
      vpc_id     = module.vpc_bodegas[name].vpc_id
    }
  }
}

output "ssh_commands" {
  description = "Comandos listos para conectarse por SSH a cada bodega"
  value = {
    for name, instance in module.ec2_bodegas : name => "ssh -i vockey.pem ec2-user@${instance.public_ip}"
  }
}

output "ecs_central_cluster" {
  description = "Datos del Cluster ECS de la Bodega Central"
  value = {
    name = module.ecs_central.cluster_name
    arn  = module.ecs_central.cluster_arn
  }
}

output "vpc_central" {
  description = "Datos de la VPC Central"
  value = {
    vpc_id     = module.vpc_central.vpc_id
    cidr_block = module.vpc_central.vpc_cidr_block
  }
}
