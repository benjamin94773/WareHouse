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

  tags = {
    Name = var.instance_name
  }
}
