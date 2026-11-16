terraform {
  required_version = ">= 1.7.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.4"
    }
  }
}

provider "aws" {
  region  = var.aws_region
  profile = "lab1"
}

# ==============================================================================
# 1. RED CENTRAL (VPC 10.0.0.0/16) Y EC2 DE LA PLATAFORMA CENTRAL
# ==============================================================================

module "vpc_central" {
  source              = "./modules/vpc"
  name                = "vpc-central"
  vpc_cidr            = "10.0.0.0/16"
  public_subnet_cidr  = "10.0.1.0/24"
  private_subnet_cidr = "10.0.2.0/24"
}

resource "aws_security_group" "sg_central" {
  name        = "secgroup-central"
  description = "Security Group para Bodega Central (API central, RabbitMQ y read model)"
  vpc_id      = module.vpc_central.vpc_id

  ingress {
    description = "SSH para administracion"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "API central y dashboard (http://IP:8080)"
    from_port   = 8080
    to_port     = 8080
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "RabbitMQ AMQP solo desde las VPCs de las bodegas y la central"
    from_port   = 5672
    to_port     = 5672
    protocol    = "tcp"
    cidr_blocks = ["10.0.0.0/8"]
  }

  ingress {
    description = "RabbitMQ Management (http://IP:15672)"
    from_port   = 15672
    to_port     = 15672
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    description = "Permitir todo el trafico de salida"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "sg-central"
  }
}

# EC2 de la plataforma central: RabbitMQ, API central, workers y read model (PostgreSQL)
module "ec2_central" {
  source                 = "./modules/ec2"
  instance_name          = "central"
  ami_id                 = var.ami_id
  instance_type          = var.instance_type
  key_name               = var.key_name
  subnet_id              = module.vpc_central.public_subnet_id
  vpc_security_group_ids = [aws_security_group.sg_central.id]
  iam_instance_profile   = var.instance_profile
  user_data              = templatefile("${path.module}/scripts/install_docker.sh.tftpl", { role = "central" })
}

# ==============================================================================
# 2. REDES DE LAS BODEGAS (UNA VPC INDEPENDIENTE POR BODEGA CON FOR_EACH)
# Cada bodega tiene su propio espacio de red aislado con subred pública y privada.
# ==============================================================================

module "vpc_bodegas" {
  source   = "./modules/vpc"
  for_each = var.warehouses

  name                = "vpc-${each.key}"
  vpc_cidr            = each.value.vpc_cidr
  public_subnet_cidr  = each.value.public_subnet_cidr
  private_subnet_cidr = each.value.private_subnet_cidr
}

# ==============================================================================
# 3. GRUPOS DE SEGURIDAD DE LAS BODEGAS (CON FOR_EACH)
# Permite administracion por SSH, APIs y trafico entrante exclusivo desde Central.
# ==============================================================================

resource "aws_security_group" "sg_bodegas" {
  for_each    = var.warehouses
  name        = "secgroup-${each.key}"
  description = "Security Group para Bodega ${each.key}"
  vpc_id      = module.vpc_bodegas[each.key].vpc_id

  ingress {
    description = "SSH para administracion"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "Load balancer Nginx de la bodega (API y frontend)"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }



  ingress {
    description = "Trafico entrante exclusivo desde Bodega Central (10.0.0.0/16)"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = [module.vpc_central.vpc_cidr_block]
  }

  egress {
    description = "Salida a Internet para descargar paquetes e imagenes Docker"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "sg-${each.key}"
  }
}

# ==============================================================================
# 4. INTERCONEXIÓN HUB-AND-SPOKE (PEERING CENTRAL <-> BODEGAS CON FOR_EACH)
# Central conectada a cada bodega. Las bodegas NO tienen peering entre sí (aisladas).
# ==============================================================================

resource "aws_vpc_peering_connection" "central_to_bodegas" {
  for_each    = var.warehouses
  vpc_id      = module.vpc_central.vpc_id
  peer_vpc_id = module.vpc_bodegas[each.key].vpc_id
  auto_accept = true

  tags = {
    Name = "peering-central-to-${each.key}"
  }
}

# Rutas desde Central hacia cada Bodega
resource "aws_route" "central_to_bodegas" {
  for_each                  = var.warehouses
  route_table_id            = module.vpc_central.public_route_table_id
  destination_cidr_block    = module.vpc_bodegas[each.key].vpc_cidr_block
  vpc_peering_connection_id = aws_vpc_peering_connection.central_to_bodegas[each.key].id
}

# Rutas desde cada Bodega de regreso hacia Central
resource "aws_route" "bodegas_to_central" {
  for_each                  = var.warehouses
  route_table_id            = module.vpc_bodegas[each.key].public_route_table_id
  destination_cidr_block    = module.vpc_central.vpc_cidr_block
  vpc_peering_connection_id = aws_vpc_peering_connection.central_to_bodegas[each.key].id
}

# ==============================================================================
# 5. INSTANCIAS EC2 DE LAS BODEGAS (CREADAS CON FOR_EACH)
# Recorre los nombres del mapa (wh-001, wh-002, wh-003) y les asigna su subnet,
# security group y el script de User Data que instala Docker.
# ==============================================================================

module "ec2_bodegas" {
  source   = "./modules/ec2"
  for_each = var.warehouses

  instance_name          = each.key
  ami_id                 = var.ami_id
  key_name               = var.key_name
  subnet_id              = module.vpc_bodegas[each.key].public_subnet_id
  vpc_security_group_ids = [aws_security_group.sg_bodegas[each.key].id]
  instance_type          = var.instance_type
  iam_instance_profile   = var.instance_profile
  user_data              = templatefile("${path.module}/scripts/install_docker.sh.tftpl", { role = each.key })
}

# ==============================================================================
# 6. ALMACENAMIENTO HISTÓRICO (S3) PARA REPORTES Y SNAPSHOTS DEL BATCH
# ==============================================================================

# Se crea con CloudFormation: en AWS Academy el recurso aws_s3_bucket de Terraform falla al
# leer la configuración de Object Lock (bloqueada por una SCP del laboratorio).
data "aws_caller_identity" "current" {}

locals {
  bucket_name = "warehouse-platform-${data.aws_caller_identity.current.account_id}"
}

resource "aws_cloudformation_stack" "platform_bucket" {
  name = "warehouse-platform-bucket"

  template_body = jsonencode({
    Resources = {
      Bucket = {
        Type           = "AWS::S3::Bucket"
        DeletionPolicy = "Delete"
        Properties = {
          BucketName = local.bucket_name
          PublicAccessBlockConfiguration = {
            BlockPublicAcls       = true
            BlockPublicPolicy     = true
            IgnorePublicAcls      = true
            RestrictPublicBuckets = true
          }
        }
      }
    }
    Outputs = { BucketName = { Value = { Ref = "Bucket" } } }
  })
}

# ==============================================================================
# 7. LAMBDA: VALIDA CADA REPORTE QUE EL BATCH ESCRIBE EN reports/ (S3 ObjectCreated)
# ==============================================================================

# En AWS Academy no se pueden crear roles IAM; se usa el LabRole existente
data "aws_iam_role" "lab" {
  name = "LabRole"
}

data "archive_file" "report_validator" {
  type        = "zip"
  source_file = "${path.module}/lambda/report_validator/handler.py"
  output_path = "${path.module}/.build/report_validator.zip"
}

resource "aws_lambda_function" "report_validator" {
  function_name    = "warehouse-report-validator"
  role             = data.aws_iam_role.lab.arn
  runtime          = "python3.13"
  handler          = "handler.lambda_handler"
  filename         = data.archive_file.report_validator.output_path
  source_code_hash = data.archive_file.report_validator.output_base64sha256
  timeout          = 15

  environment {
    variables = {
      CENTRAL_URL = "http://${module.ec2_central.public_ip}:8080"
    }
  }
}

# S3 -> EventBridge -> Lambda. La notificación directa S3 -> Lambda no entrega eventos en el
# Learner Lab; EventBridge sí, y además permite filtrar por prefijo con un patrón.
resource "aws_s3_bucket_notification" "reports" {
  bucket      = aws_cloudformation_stack.platform_bucket.outputs["BucketName"]
  eventbridge = true
}

resource "aws_cloudwatch_event_rule" "report_created" {
  name        = "warehouse-report-created"
  description = "Objeto .json creado en reports/ del bucket de la plataforma"
  event_pattern = jsonencode({
    source      = ["aws.s3"]
    detail-type = ["Object Created"]
    detail = {
      bucket = { name = [local.bucket_name] }
      object = { key = [{ wildcard = "reports/*.json" }] }
    }
  })
}

resource "aws_cloudwatch_event_target" "report_validator" {
  rule = aws_cloudwatch_event_rule.report_created.name
  arn  = aws_lambda_function.report_validator.arn
}

resource "aws_lambda_permission" "allow_eventbridge" {
  statement_id  = "AllowEventBridgeInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.report_validator.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.report_created.arn
}
