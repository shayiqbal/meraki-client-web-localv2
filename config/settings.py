"""Environment-based application settings."""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv


def user_data_dir(app_name: str = "Meraki Config Manager") -> Path:
    """Return a writable per-user data directory regardless of install location.

    On Windows this is %LOCALAPPDATA%\\<app_name>.
    Falls back to ~/.config/<app_name> on macOS/Linux.
    """
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home())
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or (Path.home() / ".local" / "share"))
    return base / app_name


@dataclass(frozen=True, slots=True)
class Settings:
    api_key: str
    max_retries: int = 4
    retry_base_seconds: float = 1.0
    early_access: bool = True
    log_path: Path = field(
        default_factory=lambda: user_data_dir() / "logs" / "vpn_exclusion_manager.jsonl"
    )

    @classmethod
    def load(cls, env_file: Path | None = None) -> "Settings":
        load_dotenv(dotenv_path=env_file or Path(".env"))
        return cls(
            api_key=os.getenv("MERAKI_DASHBOARD_API_KEY", "").strip(),
            max_retries=max(0, int(os.getenv("MERAKI_MAX_RETRIES", "4"))),
            retry_base_seconds=max(
                0.0, float(os.getenv("MERAKI_RETRY_BASE_SECONDS", "1.0"))
            ),
            early_access=os.getenv("MERAKI_ENABLE_EARLY_ACCESS", "true").lower()
            in {"1", "true", "yes", "on"},
        )

    def validate(self) -> None:
        if not self.api_key:
            raise ValueError(
                "MERAKI_DASHBOARD_API_KEY is missing. Copy .env.example to .env "
                "and add your Dashboard API key."
            )
