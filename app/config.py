from __future__ import annotations

import json
from pathlib import Path
from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = Field(default="postgresql+psycopg://postgres:postgres@localhost:5432/job_finder", alias="DATABASE_URL")
    app_host: str = Field(default="0.0.0.0", alias="APP_HOST")
    app_port: int = Field(default=5050, alias="APP_PORT")

    scan_interval_hours: int = Field(default=6, alias="SCAN_INTERVAL_HOURS")
    request_timeout_seconds: int = Field(default=25, alias="REQUEST_TIMEOUT_SECONDS")
    max_retries: int = Field(default=3, alias="MAX_RETRIES")
    scrape_headless: bool = Field(default=True, alias="SCRAPE_HEADLESS")
    proxy_server: str = Field(default="", alias="PROXY_SERVER")
    enable_board_scrapers: bool = Field(default=False, alias="ENABLE_BOARD_SCRAPERS")

    telegram_bot_token: str = Field(default="", alias="TELEGRAM_BOT_TOKEN")
    telegram_chat_id: str = Field(default="", alias="TELEGRAM_CHAT_ID")
    telegram_notify_all_jobs: bool = Field(default=False, alias="TELEGRAM_NOTIFY_ALL_JOBS")
    telegram_alert_max_per_run: int = Field(default=20, alias="TELEGRAM_ALERT_MAX_PER_RUN")

    email_host: str = Field(default="", alias="EMAIL_HOST")
    email_port: int = Field(default=587, alias="EMAIL_PORT")
    email_username: str = Field(default="", alias="EMAIL_USERNAME")
    email_password: str = Field(default="", alias="EMAIL_PASSWORD")
    email_from: str = Field(default="", alias="EMAIL_FROM")
    email_to: str = Field(default="", alias="EMAIL_TO")
    email_provider: str = Field(default="smtp", alias="EMAIL_PROVIDER")
    email_notify_all_jobs: bool = Field(default=False, alias="EMAIL_NOTIFY_ALL_JOBS")
    email_alert_max_per_run: int = Field(default=50, alias="EMAIL_ALERT_MAX_PER_RUN")

    outlook_client_id: str = Field(default="", alias="OUTLOOK_CLIENT_ID")
    outlook_tenant: str = Field(default="consumers", alias="OUTLOOK_TENANT")
    outlook_graph_scopes: str = Field(
        default="https://graph.microsoft.com/Mail.Send,https://graph.microsoft.com/User.Read",
        alias="OUTLOOK_GRAPH_SCOPES",
    )
    outlook_token_cache_file: str = Field(default=".outlook_graph_token_cache.bin", alias="OUTLOOK_TOKEN_CACHE_FILE")
    discord_bot_token: str = Field(default="", alias="DISCORD_BOT_TOKEN")
    discord_alert_channel_id: str = Field(default="", alias="DISCORD_ALERT_CHANNEL_ID")
    discord_admin_role_id: str = Field(default="", alias="DISCORD_ADMIN_ROLE_ID")
    discord_command_guild_id: str = Field(default="", alias="DISCORD_COMMAND_GUILD_ID")
    discord_alert_max_per_run: int = Field(default=50, alias="DISCORD_ALERT_MAX_PER_RUN")
    discord_sync_commands_on_startup: bool = Field(default=False, alias="DISCORD_SYNC_COMMANDS_ON_STARTUP")
    discord_validate_startup_resources: bool = Field(default=False, alias="DISCORD_VALIDATE_STARTUP_RESOURCES")
    admin_api_token: str = Field(default="", alias="ADMIN_API_TOKEN")

    default_excluded_companies: str = Field(default="EXL Services", alias="DEFAULT_EXCLUDED_COMPANIES")
    default_roles: str = Field(
        default="Data Engineer,Databricks Engineer,Azure Data Engineer,Snowflake Data Engineer",
        alias="DEFAULT_ROLES",
    )
    default_locations: str = Field(default="India,Remote", alias="DEFAULT_LOCATIONS")
    default_experience_min: int = Field(default=2, alias="DEFAULT_EXPERIENCE_MIN")
    default_experience_max: int = Field(default=5, alias="DEFAULT_EXPERIENCE_MAX")
    default_salary_min_lpa: int = Field(default=18, alias="DEFAULT_SALARY_MIN_LPA")
    default_salary_max_lpa: int = Field(default=25, alias="DEFAULT_SALARY_MAX_LPA")

    @property
    def project_root(self) -> Path:
        return Path(__file__).resolve().parents[1]

    @property
    def source_catalog_path(self) -> Path:
        return self.project_root / "config" / "source_catalog.json"

    @property
    def outlook_scope_list(self) -> List[str]:
        reserved = {"openid", "profile", "offline_access"}
        scopes = [item.strip() for item in self.outlook_graph_scopes.split(",") if item.strip()]
        return [scope for scope in scopes if scope.lower() not in reserved]

    @property
    def outlook_cache_path(self) -> Path:
        return self.project_root / self.outlook_token_cache_file

    @property
    def discord_alert_channel_id_int(self) -> int | None:
        raw = (self.discord_alert_channel_id or "").strip()
        return int(raw) if raw.isdigit() else None

    @property
    def discord_admin_role_id_int(self) -> int | None:
        raw = (self.discord_admin_role_id or "").strip()
        return int(raw) if raw.isdigit() else None

    @property
    def discord_command_guild_id_int(self) -> int | None:
        raw = (self.discord_command_guild_id or "").strip()
        return int(raw) if raw.isdigit() else None

    @property
    def role_list(self) -> List[str]:
        return [item.strip() for item in self.default_roles.split(",") if item.strip()]

    @property
    def location_list(self) -> List[str]:
        return [item.strip() for item in self.default_locations.split(",") if item.strip()]

    @property
    def excluded_company_list(self) -> List[str]:
        return [item.strip().lower() for item in self.default_excluded_companies.split(",") if item.strip()]

    def load_source_catalog(self) -> dict:
        if not self.source_catalog_path.exists():
            return {}
        with self.source_catalog_path.open("r", encoding="utf-8") as file_obj:
            return json.load(file_obj)


settings = Settings()

