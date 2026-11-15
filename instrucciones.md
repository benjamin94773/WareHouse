# Guía de la Plataforma: Bodegas Distribuidas (Hub-and-Spoke con for_each)

Infraestructura como Código (IaC) modular y automatizada con Terraform para AWS Academy.

---

## 1. Arquitectura y Dimensionamiento de Red (Right-Sizing)

| Componente | Nombre | Red (VPC CIDR) | Subred Pública (/24) | Subred Privada (/24) | IPs Disponibles |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Central** | `vpc-central` + ECS | `10.0.0.0/16` | `10.0.1.0/24` | `10.0.2.0/24` | ~65,530 |
| **Bodega 1** | `vpc-wh-001` + EC2 | `10.1.0.0/20` | `10.1.1.0/24` | `10.1.2.0/24` | ~4,090 |
| **Bodega 2** | `vpc-wh-002` + EC2 | `10.2.0.0/20` | `10.2.1.0/24` | `10.2.2.0/24` | ~4,090 |
| **Bodega 3** | `vpc-wh-003` + EC2 | `10.3.0.0/20` | `10.3.1.0/24` | `10.3.2.0/24` | ~4,090 |

### Justificación Técnica de los Bloques CIDR para el Profesor:
1. **Central (`10.0.0.0/16`):** Como nodo consolidador de la plataforma (Hub), alberga el clúster ECS, servicios analíticos y futuras cargas pesadas. Requiere un rango amplio.
2. **Bodegas (`10.X.0.0/20`):** Se aplica el principio de **Right-Sizing**. Un bloque `/20` proporciona **4,096 IPs**, más que suficiente para decenas de contenedores o dispositivos IoT, evitando el sobre-dimensionamiento de direcciones IP privadas en caso de futura interconexión con redes corporativas (VPN / Direct Connect).
3. **Mnemotecnia del 2.° Octeto:** Se preserva el segundo octeto (`10.0`, `10.1`, `10.2`, `10.3`) para identificar de inmediato el origen del tráfico en los logs de seguridad y garantizar **cero colisión o solapamiento de IPs**.
4. **Aislamiento Estricto:** Las bodegas **únicamente** tienen VPC Peering contra la VPC Central. **No existe interconexión entre bodegas**, garantizando aislamiento de fallos y dominios independientes.

---

## 2. Automatización con `for_each` y Script de Inicialización (User Data)

1. **Variables Dinámicas:** En `variables.tf`, la variable `warehouses` define las bodegas como un mapa. Si se agrega una nueva clave al mapa (ej. `"wh-004"`), Terraform crea automáticamente su VPC, Subredes, Security Group, Peering y EC2.
2. **Ajustes Avanzados (User Data):** El script `scripts/install_docker.sh.tftpl` se inyecta en el campo de **User Data** ("Detalles avanzados" de EC2). Al arrancar la instancia:
   - Actualiza el sistema operativo.
   - Instala Docker y Git.
   - Habilita e inicia el servicio Docker.
   - Asigna permisos al usuario `ec2-user`.
   - Clona automáticamente el repositorio especificado en `repo_url` dentro de `/home/ec2-user/app`.

---

## 3. Despliegue de la Infraestructura

```bash
cd ~/Documentos/cloud-computing/actividad

# 1. Inicializar Terraform
terraform init

# 2. Generar el plan de ejecución
terraform plan -var-file=terraform.tfvars -out=tfplan

# 3. Aplicar los cambios
terraform apply tfplan
```

---

## 4. Conexión por SSH a las Bodegas

Al terminar el despliegue, consulta los comandos automáticos generados por Terraform:

```bash
terraform output ssh_commands
```

O conéctate directamente con tu llave `vockey.pem`:

```bash
chmod 400 vockey.pem
ssh -i vockey.pem ec2-user@<IP_PUBLICA>
```

---

## 5. Verificar el Aprovisionamiento en las Bodegas

Una vez conectado por SSH a cualquier bodega:

```bash
# Verificar Docker
docker --version
docker ps

# Ver el registro completo del script de aprovisionamiento
cat /var/log/user-data.log

# Verificar el repositorio clonado
ls -la /home/ec2-user/app
```

---

## 6. Destruir la Infraestructura (Al terminar la práctica)

Para cuidar los créditos de AWS Academy:

```bash
terraform destroy -var-file=terraform.tfvars -auto-approve
```
