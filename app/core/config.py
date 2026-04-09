from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    supabase_url: str = ""
    supabase_service_key: str = ""
    openrouter_api_key: str = ""
    frontend_url: str = "http://localhost:5173"

    @property
    def cors_origins(self) -> List[str]:
        origins = ["http://localhost:5173"]
        if self.frontend_url and self.frontend_url not in origins:
            origins.append(self.frontend_url)
        return origins

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
