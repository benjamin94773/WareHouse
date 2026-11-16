# Fase 9 — AWS Lambda

## Objetivo

Introducir procesamiento serverless basado en eventos.

## Caso

```text
S3
 |
 | ObjectCreated
 v
Lambda
 |
 +--> validar
 +--> transformar
 +--> registrar
 +--> publicar evento
```

## Comparación

Analizar:

| Característica | Worker | Batch | Lambda |
|---|---|---|---|
| Ejecución continua | Sí | No | No |
| Activación por evento | Sí | No necesariamente | Sí |
| Escalamiento | Controlado | Controlado | Administrado |
| Estado | Externo | Externo | Externo |
| Uso | Procesamiento continuo | Procesamiento masivo | Funciones/eventos |

La tabla debe analizarse como herramienta de decisión, no como una regla absoluta.
