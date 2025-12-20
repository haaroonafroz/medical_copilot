import os
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore')

    # OpenAI
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY")

    # Qdrant
    QDRANT_URL: str = os.getenv("QDRANT_URL")
    QDRANT_API_KEY: str = os.getenv("QDRANT_API_KEY")
    QDRANT_COLLECTION_NAME: str = os.getenv("QDRANT_COLLECTION_NAME")

    # FHIR
    FHIR_BASE_URL: str = os.getenv("FHIR_BASE_URL")
    
    # Arize Phoenix
    PHOENIX_COLLECTOR_ENDPOINT: str = os.getenv("PHOENIX_COLLECTOR_ENDPOINT")

settings = Settings()

