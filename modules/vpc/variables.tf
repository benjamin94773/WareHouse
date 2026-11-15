variable "vpc_cidr" {
  description = "Rango CIDR para la VPC"
  type        = string
}

variable "public_subnet_cidr" {
  description = "Rango CIDR para la subred pública"
  type        = string
}

variable "private_subnet_cidr" {
  description = "Rango CIDR para la subred privada"
  type        = string
}

variable "availability_zone" {
  description = "Zona de disponibilidad"
  type        = string
  default     = "us-east-1a"
}

variable "name" {
  description = "Nombre identificador de la VPC"
  type        = string
}
