from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    GROQ_API_KEY: str
    SUPABASE_URL: str
    SUPABASE_KEY: str
    GMAIL_USER: str = ""
    GMAIL_APP_PASSWORD: str = ""
    FRONTEND_URL: str = "http://localhost:8080"

    class Config:
        env_file = ".env"


settings = Settings()
