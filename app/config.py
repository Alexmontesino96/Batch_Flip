from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # App
    app_name: str = "Batch Flip"
    app_env: str = "development"
    debug: bool = True

    # Database
    database_url: str = "postgresql+asyncpg://batchflip:batchflip@localhost:5432/batchflip"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Keepa API
    keepa_api_key: str = ""

    # Amazon SP-API
    sp_api_app_id: str = ""
    sp_api_client_id: str = ""
    sp_api_client_secret: str = ""
    sp_api_refresh_token: str = ""
    sp_api_seller_id: str = "A2TSJV48FRRFVQ"  # AMONCA Tecnology

    # Encryption
    encryption_key: str = ""

    # Supabase Auth
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""

    # LLM (optional, for future AI features)
    gemini_api_key: str = ""
    openai_api_key: str = ""

    # File uploads
    upload_dir: str = "uploads"

    # Batch processing
    keepa_batch_size: int = 20
    keepa_concurrency: int = 5
    resolve_concurrency: int = 10
    progress_update_interval: int = 50

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
