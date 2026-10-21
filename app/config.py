"""Environment configuration; secrets never travel to clients."""
from dataclasses import dataclass, field
from pathlib import Path
import os
import secrets
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]

@dataclass
class Settings:
    database_path: str = str(ROOT / "data" / "honocareer.db")
    jwt_secret: str = ""
    access_ttl: int = 7200
    refresh_ttl: int = 30 * 86400
    llm_provider: str = "deepseek"
    deepseek_api_key: str = field(default="", repr=False)
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"
    llm_timeout: float = 60.0
    registration_enabled: bool = True
    max_file_bytes: int = 10 * 1024 * 1024
    allowed_origins: tuple[str, ...] = ("http://localhost:8000", "http://127.0.0.1:8000")
    worker_interval: float = 0.1
    rate_limit: int = 60

    @classmethod
    def from_env(cls):
        load_dotenv(ROOT / ".env", override=False)
        return cls(
            database_path=os.getenv("DATABASE_PATH", cls.database_path),
            jwt_secret=os.getenv("JWT_SECRET", ""),
            access_ttl=int(os.getenv("ACCESS_TOKEN_TTL", "7200")),
            llm_provider=os.getenv("LLM_PROVIDER", "deepseek"),
            deepseek_api_key=os.getenv("DEEPSEEK_API_KEY", ""),
            deepseek_base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
            deepseek_model=os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
            registration_enabled=os.getenv("REGISTRATION_ENABLED", "true").lower() == "true",
            allowed_origins=tuple(x.strip() for x in os.getenv("CORS_ORIGINS", "http://localhost:8000,http://127.0.0.1:8000").split(",") if x.strip()),
        )

    def prepare(self):
        if self.llm_provider not in ("deepseek", "demo"):
            raise ValueError("LLM_PROVIDER must be deepseek or demo")
        path = Path(self.database_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        if not self.jwt_secret:
            secret_file = path.parent / ".jwt-secret"
            try:
                with secret_file.open("x", encoding="ascii") as handle:
                    handle.write(secrets.token_urlsafe(48))
            except FileExistsError:
                pass
            self.jwt_secret = secret_file.read_text(encoding="ascii").strip()
        if len(self.jwt_secret) < 32:
            raise ValueError("JWT_SECRET must contain at least 32 characters")
