from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/warehouse_db"
    WAREHOUSE_ID: str = "WH-001"  # Identificador de esta instancia autónoma

    # Configuración de RabbitMQ Broker
    RABBITMQ_HOST: str = "localhost"
    RABBITMQ_PORT: int = 5672
    RABBITMQ_USER: str = "guest"
    RABBITMQ_PASS: str = "guest"
    RABBITMQ_QUEUE: str = "warehouse_events"

    class Config:
        env_file = ".env"

settings = Settings()
