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
  description = "Comandos listos para conectarse por SSH a cada bodega (usuario ubuntu)"
  value = {
    for name, instance in merge(module.ec2_bodegas, { central = module.ec2_central }) : name => "ssh -i labsuser.pem ubuntu@${instance.public_ip}"
  }
}

output "central" {
  description = "IPs de la EC2 central (API central en :8080, RabbitMQ en :15672)"
  value = {
    id         = module.ec2_central.instance_id
    public_ip  = module.ec2_central.public_ip
    private_ip = module.ec2_central.private_ip
  }
}

output "s3_bucket" {
  description = "Bucket S3 para reportes y snapshots del batch"
  value       = aws_cloudformation_stack.platform_bucket.outputs["BucketName"]
}

output "vpc_central" {
  description = "Datos de la VPC Central"
  value = {
    vpc_id     = module.vpc_central.vpc_id
    cidr_block = module.vpc_central.vpc_cidr_block
  }
}

output "lambda_report_validator" {
  description = "Lambda que valida los reportes del batch (logs en CloudWatch)"
  value       = aws_lambda_function.report_validator.function_name
}
