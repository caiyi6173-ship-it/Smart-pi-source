from functools import lru_cache
from pathlib import Path
import os


class Settings:
    def __init__(self) -> None:
        self.app_name = "smartpi-web-backend"
        self.version = "0.1.0"
        self.database_path = Path(os.getenv("SMARTPI_WEB_DB", "data/smartpi_web.db"))


@lru_cache
def get_settings() -> Settings:
    return Settings()
