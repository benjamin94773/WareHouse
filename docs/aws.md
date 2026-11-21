# Inventario de Recursos AWS (Entregable 6 y 7)

Este documento detalla el inventario exacto de recursos de nube desplegados y aprovisionados mediante el código declarativo de Terraform (`main.tf` y módulos asociados), adaptado a las políticas de seguridad del AWS Academy Learner Lab.

---

## 1. Tabla Resumen de Recursos Aprovisionados

| Tipo de Recurso AWS | Recurso Terraform | Cantidad | Identificador / Detalle | Propósito en la Arquitectura |
|---|---|:---:|---|---|
| **VPC** | `module.vpc_central`, `module.vpc_bodegas` | **4** | `10.0.0.0/16` (Central)<br>`10.1.0.0/20` (`wh-001`)<br>`10.2.0.0/20` (`wh-002`)<br>`10.3.0.0/20` (`wh-003`) | Aislamiento perimetral completo por dominio operativo. Las bodegas no comparten red entre sí. |
| **Subredes Públicas** | `aws_subnet.public` | **4** | 1 por VPC (`/24`) | Ubicación de las instancias EC2 con acceso SSH e interfaces públicas para balanceo/API. |
| **Subredes Privadas** | `aws_subnet.private` | **4** | 1 por VPC (`/24`) | Reservadas para ampliación futura de bases de datos relacionales o clústeres privados. |
| **VPC Peering** | `aws_vpc_peering_connection.central_to_bodegas` | **3** | `peering-central-to-wh-001`<br>`peering-central-to-wh-002`<br>`peering-central-to-wh-003` | Topología **Hub-and-Spoke**: interconexión exclusiva Central $\leftrightarrow$ Bodega. |
| **Tablas y Rutas** | `aws_route.central_to_bodegas`<br>`aws_route.bodegas_to_central` | **6** | Tablas de enrutamiento asociadas al peering | Enrutamiento bidireccional punto a punto entre la Central y cada VPC de bodega. |
| **Security Groups** | `aws_security_group.sg_central`<br>`aws_security_group.sg_bodegas` | **4** | `secgroup-central`<br>`secgroup-wh-001`<br>`secgroup-wh-002`<br>`secgroup-wh-003` | Reglas de firewall: puertos de datos (5432, 5672) restringidos exclusivamente a la red privada `10.0.0.0/8`. Puertos públicos: 80 (LB bodega), 8080 (Central), 22 (SSH). |
| **Instancias EC2** | `module.ec2_central`, `module.ec2_bodegas` | **4** | `central` (1)<br>`wh-001`, `wh-002`, `wh-003` (3) | Tipo `t3.small` (2 vCPU, 2 GiB RAM). Ejecutan Docker Compose, User Data de swap y contenedores de backend. |
| **Almacenamiento S3** | `aws_cloudformation_stack.platform_bucket` | **1** | `warehouse-platform-<account_id>` | Bucket para históricos, snapshots del batch y reportes diarios. Desplegado vía CloudFormation con bloqueo público total (`PublicAccessBlock`). |
| **AWS Lambda** | `aws_lambda_function.report_validator` | **1** | `warehouse-report-validator` | Función serverless (Python 3.13) que valida reportes `.json` generados por el proceso Batch. |
| **EventBridge (CloudWatch)** | `aws_cloudwatch_event_rule.report_created`<br>`aws_cloudwatch_event_target.report_validator` | **1** | Regla para eventos `Object Created` en `reports/*.json` | Desacopla la invocación S3 $\rightarrow$ EventBridge $\rightarrow$ Lambda sin colisiones de permisos en el Learner Lab. |
| **Roles IAM** | `data.aws_iam_role.lab` | **1** | `LabRole` / `LabInstanceProfile` | Perfil IAM preconfigurado con políticas de mínimo privilegio requeridas para interactuar con S3 y EventBridge sin llaves fijas. |

---

## 2. Decisiones Técnicas del Aprovisionamiento

1. **Uso de CloudFormation para el Bucket S3:**
   * En AWS Academy Learner Lab, el recurso nativo `aws_s3_bucket` falla al intentar leer `ObjectLockConfiguration` debido a una SCP de cuenta restrictiva.
   * Se resolvió encapsulando la creación del bucket dentro de un stack de CloudFormation en `main.tf:225-246`.
2. **Topología de Red Hub-and-Spoke:**
   * Las bodegas no tienen peering entre sí: una falla en `wh-002` no tiene ruta de red hacia `wh-001` ni `wh-003`.
   * Cualquier coordinación distribuida se realiza exclusivamente a través de la plataforma Central y RabbitMQ.
3. **Escalabilidad Parametrizada (`for_each`):**
   * Toda la infraestructura de bodegas (VPCs, Subnets, Security Groups, EC2 y Peerings) se genera dinámicamente iterando sobre el mapa `var.warehouses`.
   * Agregar una nueva bodega (ej. `wh-004`) solo requiere una línea adicional en `terraform.tfvars`.
