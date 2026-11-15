variable "aws_region" {
  description = "Región de AWS para el despliegue"
  type        = string
  default     = "us-east-1"
}

variable "ami_id" {
  description = "AMI ID para las instancias EC2 de las bodegas (Amazon Linux 2023)"
  type        = string
  default     = "ami-0d97d7f07b25dd693"
}

variable "key_name" {
  description = "Nombre del Key Pair para acceso SSH"
  type        = string
  default     = "vockey"
}

variable "repo_url" {
  description = "URL del repositorio Git que clonarán las bodegas"
  type        = string
  default     = "https://github.com/SebastianReyesLeyton/cloud-computing.git"
}

# ==============================================================================
# Conjunto / Mapa de Bodegas
# Recorrido con for_each para crear las VPCs, Security Groups, Peering y EC2s.
# Usamos bloques /20 para cada bodega (4,096 IPs) bajo la práctica de Right-Sizing,
# manteniendo el segundo octeto mnemotécnico (10.1.X.X, 10.2.X.X, 10.3.X.X).
# ==============================================================================
variable "warehouses" {
  description = "Conjunto de bodegas con su nombre y direccionamiento de red"
  type = map(object({
    vpc_cidr            = string
    public_subnet_cidr  = string
    private_subnet_cidr = string
  }))
  default = {
    "wh-001" = {
      vpc_cidr            = "10.1.0.0/20"
      public_subnet_cidr  = "10.1.1.0/24"
      private_subnet_cidr = "10.1.2.0/24"
    }
    "wh-002" = {
      vpc_cidr            = "10.2.0.0/20"
      public_subnet_cidr  = "10.2.1.0/24"
      private_subnet_cidr = "10.2.2.0/24"
    }
    "wh-003" = {
      vpc_cidr            = "10.3.0.0/20"
      public_subnet_cidr  = "10.3.1.0/24"
      private_subnet_cidr = "10.3.2.0/24"
    }
  }
}
