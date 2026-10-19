from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "mysql+pymysql://root:password@localhost:3306/campus_fix"
    jwt_secret: str = "dev-only-secret-change-me"
    jwt_expire_minutes: int = 60
    cors_origins: str = "http://localhost:5173"
    frontend_url: str = "http://localhost:5173"
    upload_dir: str = "uploads"
    backup_dir: str = "backups"
    max_upload_mb: int = 5
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""

    initial_admin_email: str = ""
    initial_admin_name: str = ""
    initial_admin_password: str = ""

    @property
    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
