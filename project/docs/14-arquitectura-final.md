# Arquitectura Final de Referencia

```text
                              INTERNET
                                  |
                           +------+------+
                           |Load Balancer|
                           +------+------+
                                  |
                            +-----+-----+
                            | Central   |
                            |   API     |
                            +-----+-----+
                                  |
                     +------------+------------+
                     |                         |
                 Read Model                RabbitMQ
                     |                         |
                     |            +------------+------------+
                     |            |            |            |
                     |         Workers      Workers      Workers
                     |
        +------------+------------+------------+
        |                         |            |
        v                         v            v
  Warehouse A              Warehouse B   Warehouse C
        |                         |            |
   +----+----+               +----+----+  +----+----+
   |         |               |         |  |         |
  API      Redis             API      Redis API   Redis
   |         |               |         |  |         |
   v         |               v         |  v         |
PostgreSQL   |          PostgreSQL    | PostgreSQL |
   |         |               |         |  |         |
   +---------+---------------+---------+--+---------+
                       |
                    Events
                       |
                   RabbitMQ
                       |
              +--------+--------+
              |                 |
              v                 v
             S3              Lambda
              |
              v
           Batch
```

## Principios

### 1. Cada bodega es autónoma

Tiene su propio estado operacional.

### 2. La central consolida

La central no necesita ejecutar cada operación de inventario de cada bodega.

### 3. Los eventos desacoplan

Los efectos secundarios pueden ejecutarse de manera asíncrona.

### 4. Redis acelera lecturas

Pero no debe considerarse la fuente principal de verdad del inventario.

### 5. PostgreSQL mantiene operaciones transaccionales

Dentro del dominio de cada bodega.

### 6. RabbitMQ permite desacoplamiento

Pero introduce nuevos problemas:

- duplicados;
- reintentos;
- orden;
- DLQ;
- observabilidad.

### 7. El Read Model acepta consistencia eventual

La consulta global puede no reflejar instantáneamente la última operación.

### 8. Saga coordina transferencias

Porque una transferencia cruza límites de datos independientes.

### 9. La observabilidad es transversal

Cada operación distribuida necesita trazabilidad.

### 10. IoT es una extensión

Primero se entiende la plataforma distribuida; después se incorpora el mundo físico.
