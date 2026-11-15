variable "instance_type" {
  description = "Tipo de instancia para el servidor EC2"
  type        = string
  default     = "t3.micro"
}

variable "ami_id" {
  description = "AMI ID para la instancia EC2"
  type        = string
  default     = "ami-0d97d7f07b25dd693"
}

variable "instance_name" {
  description = "Nombre asignado a la instancia EC2"
  type        = string
}

variable "subnet_id" {
  description = "ID de la subred donde se desplegará la instancia"
  type        = string
}

variable "vpc_security_group_ids" {
  description = "Lista de Security Group IDs a asociar"
  type        = list(string)
}

variable "key_name" {
  description = "Nombre del Key Pair para acceso SSH"
  type        = string
  default     = "vockey"
}

variable "user_data" {
  description = "Script de User Data para aprovisionamiento"
  type        = string
  default     = null
}
