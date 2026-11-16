# Contexto de build: app/src (para incluir el paquete compartido shared/)
FROM python:3.13-slim

WORKDIR /app

COPY backend/app/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY shared ./shared
COPY backend/app/app ./app
COPY backend/app/main.py main.py

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
