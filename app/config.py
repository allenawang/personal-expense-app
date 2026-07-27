"""Application settings.

Everything configurable lives here so no other module reads os.environ directly.

The app runs unchanged on Azure App Service, Render, Railway, Fly.io, or a
laptop. The only thing that differs between them is where the database lives,
which is worked out once, below.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


def detect_platform() -> str:
    """Identify the host from the environment variables it sets."""
    if os.environ.get("WEBSITE_INSTANCE_ID"):
        return "azure"          # Azure App Service
    if os.environ.get("RENDER"):
        return "render"
    if os.environ.get("RAILWAY_ENVIRONMENT"):
        return "railway"
    if os.environ.get("FLY_APP_NAME"):
        return "fly"
    return "local"


def default_data_dir(platform: str) -> Path:
    """Where a SQLite file can live and survive a restart.

    Azure  /home is the persistent mount (needs WEBSITES_ENABLE_APP_SERVICE_STORAGE).
    Render /var/data is where an attached disk mounts by default.
    Fly    /data is the conventional volume mount point.

    Railway has no persistent disk on the free plan, so SQLite there is
    temporary — set DATABASE_URL to a Postgres instance instead.
    """
    return {
        "azure": Path("/home/data"),
        "render": Path(os.environ.get("RENDER_DISK_PATH", "/var/data")),
        "fly": Path("/data"),
    }.get(platform, Path("data"))


PLATFORM = detect_platform()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Ledger"
    currency_symbol: str = "$"

    # Set this to use Postgres instead of SQLite. Managed Postgres providers
    # hand out postgres:// URLs, which SQLAlchemy needs as postgresql+psycopg://
    # — the conversion is handled below, so paste the URL as given.
    database_url: str = ""

    # Categories created the first time the database is empty.
    seed_on_first_run: bool = True

    @property
    def platform(self) -> str:
        return PLATFORM

    @property
    def resolved_database_url(self) -> str:
        if self.database_url:
            return self._normalise(self.database_url)

        data_dir = default_data_dir(PLATFORM)
        try:
            data_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            # No writable disk at that path (a container with no volume
            # attached). Fall back to the working directory so the app still
            # starts — the data won't survive a restart, which is why the
            # README recommends Postgres on ephemeral hosts.
            data_dir = Path("data")
            data_dir.mkdir(parents=True, exist_ok=True)

        return f"sqlite:///{(data_dir / 'ledger.db').as_posix()}"

    @staticmethod
    def _normalise(url: str) -> str:
        """Accept the Postgres URL formats providers actually hand out."""
        if url.startswith("postgres://"):
            return url.replace("postgres://", "postgresql+psycopg://", 1)
        if url.startswith("postgresql://"):
            return url.replace("postgresql://", "postgresql+psycopg://", 1)
        return url


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
