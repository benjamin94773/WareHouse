# 🏢 Warehouse Cloud Platform — Infraestructura IaC con Terraform

Repositorio oficial del equipo para el despliegue de la **Plataforma Distribuida Multi-Bodega (*Warehouse Cloud Platform*)**, desplegada en **Amazon Web Services (AWS)** mediante **Terraform**.

---

## 👥 Guía Rápida para Compañeros de Equipo (Despliegue idéntico en 3 pasos)

Si eres un integrante del equipo y quieres tener exactamente la misma infraestructura en tu propia cuenta de AWS Academy:

### 1. Clonar este repositorio
```bash
git clone https://github.com/benjamin94773/WareHouse.git
cd WareHouse
```

### 2. Configurar tus credenciales de AWS Academy
1. En tu AWS Academy Learner Lab, dale a **Start Lab** (espera el círculo verde).
2. Haz clic en **AWS Details** -> **Show** en la sección **AWS CLI**.
3. Copia ese texto y pégalo en tu archivo `~/.aws/credentials` con el encabezado `[lab1]`:
   ```ini
   [lab1]
   aws_access_key_id = ASIA...
   aws_secret_access_key = ...
   aws_session_token = ...
   ```
4. Descarga tu archivo de llave privada (`labsuser.pem`) de AWS Details, guárdalo dentro de la carpeta del proyecto y dale permisos:
   ```bash
   chmod 400 labsuser.pem
   ```

### 3. Desplegar en AWS
```bash
# 1. Inicializar plugins
terraform init

# 2. Desplegar toda la infraestructura
terraform apply -var-file=terraform.tfvars
```
*(Escribe `yes` cuando lo solicite y en 2 minutos tendrás toda la red, peerings y servidores arriba).*

---

## 📐 Arquitectura de Red (Hub-and-Spoke con Right-Sizing)

```mermaid
flowchart TD
    subgraph Central["VPC Central (10.0.0.0/16) - HUB"]
        ECS["Cluster Amazon ECS\n(bodega-central-cluster)"]
        SGCentral["Security Group Central\n(Puertos: 80, 8080, 5672 AMQP, 15672 Web)"]
    end

    subgraph WH1["VPC Bodega 1 (10.1.0.0/20) - SPOKE 1"]
        EC2_1["EC2: wh-001\n(Docker + Outbox Worker)"]
        SG_1["Security Group wh-001"]
    end

    subgraph WH2["VPC Bodega 2 (10.2.0.0/20) - SPOKE 2"]
        EC2_2["EC2: wh-002\n(Docker + Outbox Worker)"]
        SG_2["Security Group wh-002"]
    end

    subgraph WH3["VPC Bodega 3 (10.3.0.0/20) - SPOKE 3"]
        EC2_3["EC2: wh-003\n(Docker + Outbox Worker)"]
        SG_3["Security Group wh-003"]
    end

    %% Conexiones Peering autorizadas
    Central <-->|"VPC Peering 1"| WH1
    Central <-->|"VPC Peering 2"| WH2
    Central <-->|"VPC Peering 3"| WH3

    %% Aislamiento
    WH1 -. "❌ Sin comunicación" .- WH2
    WH2 -. "❌ Sin comunicación" .- WH3
    WH1 -. "❌ Sin comunicación" .- WH3
```

---

## 🔑 Conectarse por SSH a las Instancias EC2

El sistema utiliza la imagen Ubuntu Server. Para conectarte a cualquier bodega utiliza el usuario **`ubuntu`**:

```bash
# Conectar a Bodega 1
ssh -i labsuser.pem ubuntu@<IP_PUBLICA_WH001>

# Conectar a Bodega 2
ssh -i labsuser.pem ubuntu@<IP_PUBLICA_WH002>

# Conectar a Bodega 3
ssh -i labsuser.pem ubuntu@<IP_PUBLICA_WH003>
```

Una vez dentro:
```bash
# Verificar Docker instalado
docker --version
docker compose version

# Verificar el código del repositorio listo
ls -la /home/ubuntu/app
```

---

## 🛑 Destruir la Infraestructura (Limpiar el Lab de AWS)

Para no consumir los créditos de AWS Academy al terminar:

```bash
terraform destroy -var-file=terraform.tfvars
```
*(Escribe `yes` cuando lo solicite y Terraform eliminará automáticamente los 49 recursos).*
