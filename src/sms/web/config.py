import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional

DEFAULT_STATIC_DIR = Path(__file__).resolve().parents[3] / "web" / "dist"


@dataclass
class AppConfig:
    database_url: str
    secret_key: str
    teacher_password: Optional[str]  # None: the website's own password (set in the first-run wizard)
    storage_dir: Path
    embedded_worker: bool = True
    env: Dict[str, str] = field(default_factory=dict)
    static_dir: Optional[Path] = None

    @classmethod
    def from_env(cls) -> "AppConfig":
        secret = os.environ.get("SECRET_KEY")
        if not secret:
            raise RuntimeError("SECRET_KEY must be set")
        # Optional since the first-run wizard: when blank, the password lives on the settings row.
        password = (os.environ.get("TEACHER_PASSWORD") or "").strip() or None
        return cls(
            database_url=os.environ.get("DATABASE_URL", "sqlite:///sms.db"),
            secret_key=secret,
            teacher_password=password,
            storage_dir=Path(os.environ.get("STORAGE_DIR", "./data")),
            embedded_worker=os.environ.get("SMS_EMBEDDED_WORKER", "1") != "0",
            env={k: v for k, v in os.environ.items() if k.startswith("LLM_")},
            static_dir=Path(os.environ["SMS_STATIC_DIR"]) if os.environ.get("SMS_STATIC_DIR") else DEFAULT_STATIC_DIR,
        )
