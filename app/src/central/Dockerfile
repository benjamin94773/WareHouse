# Contexto de build: app/src (para incluir el paquete compartido shared/)
FROM python:3.13-slim

WORKDIR /app

COPY central/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY shared ./shared
COPY central/*.py central/index.html ./

EXPOSE 8080

# El mismo imagen corre la API (por defecto) o los workers: command: ["python", "worker.py"]
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
