"""Application configuration loader."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _to_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _to_int(value: str | None, default: int) -> int:
    if not value:
        return default
    return int(value)


@dataclass(slots=True)
class Settings:
    bot_token: str
    api_id: int
    api_hash: str
    public_base_url: str
    server_host: str
    server_port: int
    database_path: Path
    storage_path: Path
    hls_path: Path
    pyrogram_workdir: Path
    link_signing_secret: str
    default_link_expiry_seconds: int
    admin_ids: set[int]
    rate_limit_requests: int
    rate_limit_window_seconds: int
    max_file_size_mb: int
    download_timeout_seconds: int
    log_level: str
    ffmpeg_enabled: bool

    @classmethod
    def from_env(cls) -> "Settings":
        bot_token = os.getenv("BOT_TOKEN", "").strip()
        api_hash = os.getenv("API_HASH", "").strip()
        api_id = _to_int(os.getenv("API_ID"), 0)

        if not bot_token:
            raise ValueError("BOT_TOKEN is required")
        if not api_hash:
            raise ValueError("API_HASH is required")
        if not api_id:
            raise ValueError("API_ID is required")

        server_port = _to_int(os.getenv("PORT"), 8080)
        public_base_url = os.getenv("PUBLIC_BASE_URL", f"http://127.0.0.1:{server_port}").rstrip("/")
        admin_ids = {
            int(raw.strip())
            for raw in os.getenv("ADMIN_IDS", "").split(",")
            if raw.strip().isdigit()
        }

        link_signing_secret = os.getenv("LINK_SIGNING_SECRET", "").strip()
        if not link_signing_secret:
            # Practical fallback for local development only.
            link_signing_secret = f"dev-{bot_token}"

        settings = cls(
            bot_token=bot_token,
            api_id=api_id,
            api_hash=api_hash,
            public_base_url=public_base_url,
            server_host=os.getenv("SERVER_HOST", "0.0.0.0"),
            server_port=server_port,
            database_path=Path(os.getenv("DATABASE_PATH", "data/bot.db")),
            storage_path=Path(os.getenv("STORAGE_PATH", "storage/files")),
            hls_path=Path(os.getenv("HLS_PATH", "storage/hls")),
            pyrogram_workdir=Path(os.getenv("PYROGRAM_WORKDIR", ".pyrogram")),
            link_signing_secret=link_signing_secret,
            default_link_expiry_seconds=_to_int(os.getenv("LINK_EXPIRY_SECONDS"), 24 * 60 * 60),
            admin_ids=admin_ids,
            rate_limit_requests=_to_int(os.getenv("RATE_LIMIT_REQUESTS"), 8),
            rate_limit_window_seconds=_to_int(os.getenv("RATE_LIMIT_WINDOW_SECONDS"), 60),
            max_file_size_mb=_to_int(os.getenv("MAX_FILE_SIZE_MB"), 2048),
            download_timeout_seconds=_to_int(os.getenv("DOWNLOAD_TIMEOUT_SECONDS"), 60 * 60),
            log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
            ffmpeg_enabled=_to_bool(os.getenv("FFMPEG_ENABLED"), True),
        )
        settings.ensure_directories()
        return settings

    def ensure_directories(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.hls_path.mkdir(parents=True, exist_ok=True)
        self.pyrogram_workdir.mkdir(parents=True, exist_ok=True)
