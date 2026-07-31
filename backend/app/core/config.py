from pydantic_settings import BaseSettings
from dotenv import load_dotenv

load_dotenv()

class Settings(BaseSettings):
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    upload_dir: str = "data/uploads"
    chroma_dir: str = "data/chroma"
    reports_dir: str = "data/reports"
    chunk_size: int = 500
    chunk_overlap: int = 50
    embedding_model: str = "all-MiniLM-L6-v2"
    # How many chunks to analyse in a single LLM call. Higher is cheaper
    # and faster but the model gets sloppier as the batch grows.
    analysis_batch_size: int = 5
    # Let the model search the web for market context during an
    # assessment. Turn off to save cost or when running offline.
    enable_web_search: bool = True
    # Comma-separated list of browser origins allowed to call the API.
    cors_origins: str = "http://localhost:3000"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()