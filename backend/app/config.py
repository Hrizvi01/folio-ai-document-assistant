from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')
    data_dir: Path = Path('data')
    ollama_url: str = 'http://localhost:11434'
    chat_model: str = 'llama3.2:3b'
    embedding_model: str = 'nomic-embed-text'
    max_upload_mb: int = 20
    max_text_chars: int = 2_000_000
    retrieval_k: int = 5
    cors_origins: list[str] = ['http://localhost:5173', 'http://127.0.0.1:5173']


settings = Settings()
