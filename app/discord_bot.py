from __future__ import annotations

import asyncio
import re
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Callable

import discord
from discord import app_commands

from app.config import settings
from app.logging_utils import log_event
from app.scan_queue import TERMINAL_SCAN_STATUSES


LIST_KEYS = {"roles", "locations", "skills", "scan_times", "excluded_companies"}
INT_KEYS = {"experience_min", "experience_max", "salary_min_lpa", "salary_max_lpa", "scan_interval_hours"}
BOOL_KEYS = {"auto_run_enabled"}
TIME_PATTERN = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")
REQUEST_POLL_SECONDS = 5
REQUEST_POLL_ATTEMPTS = 180


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in (value or "").replace("\n", ",").split(",") if item.strip()]


def _parse_bool(value: str) -> bool:
    normalized = (value or "").strip().lower()
    if normalized in {"true", "1", "yes", "y", "on"}:
        return True
    if normalized in {"false", "0", "no", "n", "off"}:
        return False
    raise ValueError("Use true/false for boolean fields.")


def _normalize_value(key: str, value: str) -> Any:
    if key in LIST_KEYS:
        values = _split_csv(value)
        if key == "scan_times":
            invalid = [item for item in values if not TIME_PATTERN.match(item)]
            if invalid:
                raise ValueError(f"Invalid scan time(s): {', '.join(invalid)}. Use HH:MM in 24-hour format.")
        return values
    if key in INT_KEYS:
        parsed = int(value)
        if key == "scan_interval_hours" and parsed < 1:
            raise ValueError("scan_interval_hours must be >= 1.")
        if key != "scan_interval_hours" and parsed < 0:
            raise ValueError(f"{key} must be >= 0.")
        return parsed
    if key in BOOL_KEYS:
        return _parse_bool(value)
    raise ValueError(f"Unsupported setting key: {key}")


def _preview(value: Any, max_chars: int = 500) -> str:
    if isinstance(value, list):
        text = ", ".join(str(item) for item in value) if value else "(empty)"
    else:
        text = str(value)
    return text[:max_chars] + ("..." if len(text) > max_chars else "")


def _profile_summary(profile: dict[str, Any]) -> str:
    lines = [
        "Current Search Profile",
        f"roles: {_preview(profile.get('roles', []), 250)}",
        f"locations: {_preview(profile.get('locations', []), 250)}",
        f"skills: {_preview(profile.get('skills', []), 250)}",
        f"experience_min: {profile.get('experience_min', 0)}",
        f"experience_max: {profile.get('experience_max', 0)}",
        f"salary_min_lpa: {profile.get('salary_min_lpa', 0)}",
        f"salary_max_lpa: {profile.get('salary_max_lpa', 0)}",
        f"auto_run_enabled: {profile.get('auto_run_enabled', True)}",
        f"scan_interval_hours: {profile.get('scan_interval_hours', settings.scan_interval_hours)}",
        f"scan_times: {_preview(profile.get('scan_times', []), 250)}",
        f"excluded_companies: {_preview(profile.get('excluded_companies', []), 250)}",
    ]
    text = "\n".join(lines)
    return text[:1900]


def _format_scan_status(request: dict[str, Any]) -> str:
    result = request.get("result_payload") or {}
    lines = [
        f"request_id={request.get('id')}",
        f"status={request.get('status')}",
        f"trigger_source={request.get('trigger_source')}",
    ]
    if request.get("started_at"):
        lines.append(f"started_at={request.get('started_at')}")
    if request.get("finished_at"):
        lines.append(f"finished_at={request.get('finished_at')}")
    if request.get("error_message"):
        lines.append(f"error={request.get('error_message')}")
    if request.get("status") == "completed":
        lines.append(
            "result="
            f"run_id={result.get('run_id')} | fetched={result.get('fetched')} | inserted={result.get('inserted')} | "
            f"qualified={result.get('qualified')} | super_priority={result.get('super_priority')}"
        )
    elif request.get("status") == "failed":
        lines.append(
            "result="
            f"run_id={result.get('run_id')} | fetched={result.get('fetched')} | inserted={result.get('inserted')} | "
            f"qualified={result.get('qualified')}"
        )
    return "\n".join(lines)[:1900]


class DiscordBotService:
    def __init__(
        self,
        get_profile: Callable[[], dict[str, Any]],
        update_profile: Callable[[dict[str, Any]], dict[str, Any]],
        enqueue_scan: Callable[..., tuple[dict[str, Any], bool]],
        get_scan_request: Callable[[str], dict[str, Any] | None],
    ) -> None:
        self._get_profile = get_profile
        self._update_profile = update_profile
        self._enqueue_scan = enqueue_scan
        self._get_scan_request = get_scan_request
        self._task: asyncio.Task | None = None
        self._synced = False
        self._stopping = False
        self._healthy = False
        self._last_error = ""
        self._last_ready_at: str | None = None
        self._last_disconnect_at: str | None = None
        self._validated_alert_channel = False
        self._validated_command_guild = False

        intents = discord.Intents.default()
        self.client = discord.Client(intents=intents)
        self.tree = app_commands.CommandTree(self.client)
        self._register_events()
        self._register_commands()

    def health_snapshot(self) -> dict[str, Any]:
        return {
            "status": "ok" if self._healthy else "degraded",
            "healthy": self._healthy,
            "synced": self._synced,
            "validated_alert_channel": self._validated_alert_channel,
            "validated_command_guild": self._validated_command_guild,
            "last_ready_at": self._last_ready_at,
            "last_disconnect_at": self._last_disconnect_at,
            "last_error": self._last_error,
            "discord_user": str(self.client.user) if self.client.user else "",
        }

    def _set_unhealthy(self, error_message: str) -> None:
        self._healthy = False
        self._last_error = error_message
        log_event("discord_bot_unhealthy", level="warning", error=error_message)

    def _mark_healthy(self) -> None:
        self._healthy = True
        self._last_error = ""
        self._last_ready_at = datetime.now(timezone.utc).isoformat()

    def _handle_task_done(self, task: asyncio.Task) -> None:
        if task.cancelled():
            log_event("discord_bot_task_cancelled")
            return
        try:
            exc = task.exception()
        except BaseException as err:
            self._set_unhealthy(f"Discord bot task status check failed: {err}")
            return
        if exc:
            self._set_unhealthy(f"Discord bot task exited with error: {exc}")
        else:
            log_event("discord_bot_task_exited")

    async def _run_client_forever(self, token: str) -> None:
        retry_delay_seconds = 5
        while not self._stopping:
            try:
                await self.client.start(token)
                if self._stopping:
                    return
                self._set_unhealthy("Discord client stopped unexpectedly. Restarting.")
            except discord.errors.LoginFailure as exc:
                self._set_unhealthy(f"Discord bot login failed: {exc}")
                return
            except Exception as exc:
                if self._stopping:
                    return
                self._set_unhealthy(f"Discord bot connection failed: {exc}")
            await asyncio.sleep(retry_delay_seconds)

    def _is_authorized(self, interaction: discord.Interaction) -> bool:
        member = interaction.user
        permissions = getattr(member, "guild_permissions", None)
        if permissions and permissions.administrator:
            return True
        admin_role_id = settings.discord_admin_role_id_int
        if not admin_role_id:
            return True
        roles = getattr(member, "roles", [])
        return any(getattr(role, "id", 0) == admin_role_id for role in roles)

    async def _deny(self, interaction: discord.Interaction) -> None:
        message = "You are not allowed to use this command."
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)

    async def _require_authorized(self, interaction: discord.Interaction) -> bool:
        if self._is_authorized(interaction):
            return True
        await self._deny(interaction)
        return False

    async def _validate_startup_configuration(self) -> None:
        channel_id = settings.discord_alert_channel_id_int
        if not channel_id:
            raise RuntimeError("DISCORD_ALERT_CHANNEL_ID is missing or invalid.")
        channel = self.client.get_channel(channel_id)
        if channel is None:
            channel = await self.client.fetch_channel(channel_id)
        self._validated_alert_channel = channel is not None

        guild_id = settings.discord_command_guild_id_int
        if guild_id:
            guild = self.client.get_guild(guild_id)
            if guild is None:
                guild = await self.client.fetch_guild(guild_id)
            self._validated_command_guild = guild is not None
        else:
            self._validated_command_guild = True

    async def _track_scan_request(self, interaction: discord.Interaction, request_id: str) -> None:
        for _ in range(REQUEST_POLL_ATTEMPTS):
            await asyncio.sleep(REQUEST_POLL_SECONDS)
            request = self._get_scan_request(request_id)
            if not request:
                return
            if request.get("status") in TERMINAL_SCAN_STATUSES:
                await interaction.followup.send(_format_scan_status(request), ephemeral=True)
                return
        request = self._get_scan_request(request_id)
        if request:
            await interaction.followup.send(
                f"Scan request is still {request.get('status')}. Use /job_status request_id:{request_id}",
                ephemeral=True,
            )

    def _register_events(self) -> None:
        @self.client.event
        async def on_ready() -> None:
            try:
                await self._validate_startup_configuration()
                if not self._synced:
                    guild_id = settings.discord_command_guild_id_int
                    if guild_id:
                        guild = discord.Object(id=guild_id)
                        self.tree.copy_global_to(guild=guild)
                        synced = await self.tree.sync(guild=guild)
                        log_event("discord_commands_synced", scope="guild", guild_id=guild_id, count=len(synced))
                    else:
                        synced = await self.tree.sync()
                        log_event("discord_commands_synced", scope="global", count=len(synced))
                    self._synced = True
                self._mark_healthy()
                log_event("discord_bot_connected", user=str(self.client.user))
            except Exception as exc:
                self._set_unhealthy(f"Discord startup validation failed: {exc}")

        @self.client.event
        async def on_disconnect() -> None:
            self._last_disconnect_at = datetime.now(timezone.utc).isoformat()
            self._set_unhealthy("Discord gateway disconnected.")

        @self.client.event
        async def on_resumed() -> None:
            self._mark_healthy()
            log_event("discord_gateway_resumed")

    def _register_commands(self) -> None:
        setting_choices = [
            app_commands.Choice(name="roles", value="roles"),
            app_commands.Choice(name="locations", value="locations"),
            app_commands.Choice(name="skills", value="skills"),
            app_commands.Choice(name="experience_min", value="experience_min"),
            app_commands.Choice(name="experience_max", value="experience_max"),
            app_commands.Choice(name="salary_min_lpa", value="salary_min_lpa"),
            app_commands.Choice(name="salary_max_lpa", value="salary_max_lpa"),
            app_commands.Choice(name="auto_run_enabled", value="auto_run_enabled"),
            app_commands.Choice(name="scan_interval_hours", value="scan_interval_hours"),
            app_commands.Choice(name="scan_times", value="scan_times"),
            app_commands.Choice(name="excluded_companies", value="excluded_companies"),
        ]
        list_choices = [
            app_commands.Choice(name="roles", value="roles"),
            app_commands.Choice(name="locations", value="locations"),
            app_commands.Choice(name="skills", value="skills"),
            app_commands.Choice(name="scan_times", value="scan_times"),
            app_commands.Choice(name="excluded_companies", value="excluded_companies"),
        ]

        @self.tree.command(name="job_help", description="Show Discord job bot commands.")
        async def job_help(interaction: discord.Interaction) -> None:
            lines = [
                "Commands",
                "/job_run - Queue a scan now.",
                "/job_status request_id - Check a queued or completed scan.",
                "/job_settings - Show current settings.",
                "/job_set key value - Replace a setting value.",
                "/job_add key value - Add item(s) to a list setting.",
                "/job_remove key value - Remove item(s) from a list setting.",
                "Use comma-separated values for list fields.",
            ]
            await interaction.response.send_message("\n".join(lines), ephemeral=True)

        @self.tree.command(name="job_run", description="Queue a job scan and report the result.")
        async def job_run(interaction: discord.Interaction) -> None:
            if not await self._require_authorized(interaction):
                return
            await interaction.response.defer(ephemeral=True, thinking=True)
            request, created = self._enqueue_scan(
                trigger_source="discord",
                requested_by=str(interaction.user),
                requested_by_id=str(interaction.user.id),
                request_channel_id=str(interaction.channel_id or ""),
                request_guild_id=str(interaction.guild_id or ""),
                request_metadata={
                    "interaction_id": str(interaction.id),
                    "user_name": str(interaction.user),
                },
            )
            if created:
                await interaction.followup.send(
                    f"Queued scan request. request_id={request.get('id')}\nI will report the result here when it finishes.",
                    ephemeral=True,
                )
            else:
                await interaction.followup.send(
                    f"A scan is already {request.get('status')}. request_id={request.get('id')}",
                    ephemeral=True,
                )
            asyncio.create_task(self._track_scan_request(interaction, request.get("id", "")))

        @self.tree.command(name="job_status", description="Check the status of a queued or completed scan.")
        @app_commands.describe(request_id="Queued scan request ID")
        async def job_status(interaction: discord.Interaction, request_id: str) -> None:
            if not await self._require_authorized(interaction):
                return
            request = self._get_scan_request(request_id.strip())
            if not request:
                await interaction.response.send_message("Scan request not found.", ephemeral=True)
                return
            await interaction.response.send_message(_format_scan_status(request), ephemeral=True)

        @self.tree.command(name="job_settings", description="Show current job search profile.")
        async def job_settings(interaction: discord.Interaction) -> None:
            if not await self._require_authorized(interaction):
                return
            profile = self._get_profile()
            await interaction.response.send_message(_profile_summary(profile), ephemeral=True)

        @self.tree.command(name="job_set", description="Set any search profile field.")
        @app_commands.describe(key="Setting key", value="Value. Use comma-separated values for list settings.")
        @app_commands.choices(key=setting_choices)
        async def job_set(interaction: discord.Interaction, key: app_commands.Choice[str], value: str) -> None:
            if not await self._require_authorized(interaction):
                return
            try:
                profile = deepcopy(self._get_profile())
                profile[key.value] = _normalize_value(key.value, value)
                updated = self._update_profile(profile)
                await interaction.response.send_message(
                    f"Updated {key.value}: {_preview(updated.get(key.value))}",
                    ephemeral=True,
                )
            except Exception as exc:
                await interaction.response.send_message(f"Update failed: {exc}", ephemeral=True)

        @self.tree.command(name="job_add", description="Add values to a list setting.")
        @app_commands.describe(key="List field", value="Comma-separated values to add.")
        @app_commands.choices(key=list_choices)
        async def job_add(interaction: discord.Interaction, key: app_commands.Choice[str], value: str) -> None:
            if not await self._require_authorized(interaction):
                return
            additions = _split_csv(value)
            if not additions:
                await interaction.response.send_message("No values provided.", ephemeral=True)
                return
            try:
                profile = deepcopy(self._get_profile())
                current = profile.get(key.value) or []
                existing_lookup = {str(item).strip().lower() for item in current}
                for item in additions:
                    if item.lower() not in existing_lookup:
                        current.append(item)
                        existing_lookup.add(item.lower())
                profile[key.value] = current
                updated = self._update_profile(profile)
                await interaction.response.send_message(
                    f"Updated {key.value}: {_preview(updated.get(key.value))}",
                    ephemeral=True,
                )
            except Exception as exc:
                await interaction.response.send_message(f"Update failed: {exc}", ephemeral=True)

        @self.tree.command(name="job_remove", description="Remove values from a list setting.")
        @app_commands.describe(key="List field", value="Comma-separated values to remove.")
        @app_commands.choices(key=list_choices)
        async def job_remove(interaction: discord.Interaction, key: app_commands.Choice[str], value: str) -> None:
            if not await self._require_authorized(interaction):
                return
            removals = {item.lower() for item in _split_csv(value)}
            if not removals:
                await interaction.response.send_message("No values provided.", ephemeral=True)
                return
            try:
                profile = deepcopy(self._get_profile())
                current = profile.get(key.value) or []
                profile[key.value] = [item for item in current if str(item).strip().lower() not in removals]
                updated = self._update_profile(profile)
                await interaction.response.send_message(
                    f"Updated {key.value}: {_preview(updated.get(key.value))}",
                    ephemeral=True,
                )
            except Exception as exc:
                await interaction.response.send_message(f"Update failed: {exc}", ephemeral=True)

    async def start(self) -> None:
        token = (settings.discord_bot_token or "").strip()
        if not token:
            self._set_unhealthy("DISCORD_BOT_TOKEN is not configured.")
            return
        if self._task and not self._task.done():
            return
        self._stopping = False
        log_event("discord_bot_starting")
        self._task = asyncio.create_task(self._run_client_forever(token))
        self._task.add_done_callback(self._handle_task_done)

    async def stop(self) -> None:
        if not self._task:
            return
        self._stopping = True
        try:
            await self.client.close()
            await self._task
        except BaseException:
            pass
        finally:
            self._task = None
            self._healthy = False
