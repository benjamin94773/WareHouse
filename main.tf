terraform {
  required_version = ">= 1.7.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region  = var.aws_region
  profile = "lab1"
}

# ==============================================================================
# 1. RED CENTRAL (VPC 10.0.0.0/16) Y CLUSTER ECS
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
  description = "Security Group para Bodega Central (ECS)"
  vpc_id      = module.vpc_central.vpc_id

  ingress {
    description = "HTTP desde cualquier lugar"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "Puerto de aplicacion 8080"
    from_port   = 8080
    to_port     = 8080
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

module "ecs_central" {
  source       = "./modules/ecs"
  cluster_name = "bodega-central-cluster"
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
    description = "HTTP web"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "Puerto API contenedor 8000"
    from_port   = 8000
    to_port     = 8000
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "Puerto API contenedor 8080"
    from_port   = 8080
    to_port     = 8080
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
    description = "Salida total a Internet para descargar Docker y clonar repo"
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
# security group y el script de User Data (Ajustes avanzados) con Docker y Git.
# ==============================================================================

module "ec2_bodegas" {
  source   = "./modules/ec2"
  for_each = var.warehouses

  instance_name          = each.key
  ami_id                 = var.ami_id
  key_name               = var.key_name
  subnet_id              = module.vpc_bodegas[each.key].public_subnet_id
  vpc_security_group_ids = [aws_security_group.sg_bodegas[each.key].id]
  user_data              = templatefile("${path.module}/scripts/install_docker.sh.tftpl", { repo_url = var.repo_url })
}
