resource "aws_instance" "this" {
  ami                         = var.ami_id
  instance_type               = var.instance_type
  subnet_id                   = var.subnet_id
  vpc_security_group_ids      = var.vpc_security_group_ids
  associate_public_ip_address = true
  key_name                    = var.key_name
  user_data                   = var.user_data
  user_data_replace_on_change = true # user_data solo corre en el primer arranque
  iam_instance_profile        = var.iam_instance_profile

  # Las imágenes de Docker (Python, PostgreSQL, RabbitMQ, Redis, Nginx) no caben con holgura en 8 GB
  root_block_device {
    volume_size = var.volume_size
    volume_type = "gp3"
  }

  # IMDSv2 con hop limit 2: los contenedores (un salto de red más) pueden obtener
  # las credenciales temporales del LabInstanceProfile para escribir en S3
  metadata_options {
    http_tokens                 = "required"
    http_put_response_hop_limit = 2
  }

  tags = {
    Name = var.instance_name
  }
}
