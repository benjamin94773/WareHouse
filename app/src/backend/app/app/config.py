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

    # Redis (Cache Aside). CACHE_ENABLED=false permite medir "Redis OFF" en las pruebas de carga
    REDIS_URL: str = "redis://localhost:6379/0"
    CACHE_ENABLED: bool = True
    CACHE_TTL_SECONDS: int = 30

    class Config:
        env_file = ".env"

settings = Settings()
