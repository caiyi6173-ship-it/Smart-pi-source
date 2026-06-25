from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    agent_host: str = "127.0.0.1"
    agent_port: int = 8096
    rag_base_url: str = "http://127.0.0.1:8095"
    openclaw_base_url: str = ""
    edge_bridge_base_url: str = "http://127.0.0.1:18789"
    device_dry_run: bool = True
    agent_enable_llm_router: bool = False
    agent_request_timeout_seconds: float = Field(default=30.0, gt=0)
    tongue_class_map_path: Path = Path("../config/class_map.json")


@lru_cache
def get_settings() -> Settings:
    return Settings()
