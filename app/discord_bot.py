from __future__ import annotations

import asyncio
import re
from copy import deepcopy
from typing import Any, Awaitable, Callable

import discord
from discord import app_commands

from app.config import settings


LIST_KEYS = {"roles", "locations", "skills", "scan_times", "excluded_companies"}
INT_KEYS = {"experience_min", "experience_max", "salary_min_lpa", "salary_max_lpa", "scan_interval_hours"}
BOOL_KEYS = {"auto_run_enabled"}
TIME_PATTERN = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")


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


class DiscordBotService:
    def __init__(
        self,
        get_profile: Callable[[], dict[str, Any]],
        update_profile: Callable[[dict[str, Any]], dict[str, Any]],
        run_scan: Callable[[], Awaitable[dict[str, Any]]],
    ) -> None:
        self._get_profile = get_profile
        self._update_profile = update_profile
        self._run_scan = run_scan
        self._task: asyncio.Task | None = None
        self._synced = False
        self._stopping = False

        intents = discord.Intents.default()
        self.client = discord.Client(intents=intents)
        self.tree = app_commands.CommandTree(self.client)
        self._register_events()
        self._register_commands()

    def _handle_task_done(self, task: asyncio.Task) -> None:
        if task.cancelled():
            print("Discord bot task cancelled.")
            return
        try:
            exc = task.exception()
        except BaseException as err:
            print(f"Discord bot task status check failed: {err}")
            return
        if exc:
            print(f"Discord bot task exited with error: {exc}")
        else:
            print("Discord bot task exited.")

    async def _run_client_forever(self, token: str) -> None:
        retry_delay_seconds = 5
        while not self._stopping:
            try:
                await self.client.start(token)
                if self._stopping:
                    return
                print("Discord client stopped unexpectedly. Restarting.")
            except discord.errors.LoginFailure as exc:
                print(f"Discord bot login failed: {exc}")
                return
            except Exception as exc:
                if self._stopping:
                    return
                print(f"Discord bot connection failed: {exc}. Retrying in {retry_delay_seconds}s.")
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

    def _register_events(self) -> None:
        @self.client.event
        async def on_ready() -> None:
            if self._synced:
                return
            try:
                guild_id = settings.discord_command_guild_id_int
                if guild_id:
                    guild = discord.Object(id=guild_id)
                    self.tree.copy_global_to(guild=guild)
                    synced = await self.tree.sync(guild=guild)
                    print(f"Discord commands synced to guild {guild_id}: {len(synced)}")
                else:
                    synced = await self.tree.sync()
                    print(f"Discord global commands synced: {len(synced)}")
                self._synced = True
            except Exception as exc:
                print(f"Discord command sync failed: {exc}")
            print(f"Discord bot connected as {self.client.user}")

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
                "/job_run - Trigger scan now.",
                "/job_settings - Show current settings.",
                "/job_set key value - Replace a setting value.",
                "/job_add key value - Add item(s) to a list setting.",
                "/job_remove key value - Remove item(s) from a list setting.",
                "Use comma-separated values for list fields.",
            ]
            await interaction.response.send_message("\n".join(lines), ephemeral=True)

        @self.tree.command(name="job_run", description="Run job scan now and post alerts.")
        async def job_run(interaction: discord.Interaction) -> None:
            if not await self._require_authorized(interaction):
                return
            await interaction.response.defer(ephemeral=True, thinking=True)
            try:
                result = await self._run_scan()
                if result.get("error"):
                    message = (
                        f"Scan failed.\nrun_id={result.get('run_id')} | fetched={result.get('fetched')} | "
                        f"inserted={result.get('inserted')} | qualified={result.get('qualified')}\n"
                        f"error={result.get('error')}"
                    )
                else:
                    message = (
                        f"Scan completed.\nrun_id={result.get('run_id')} | fetched={result.get('fetched')} | "
                        f"inserted={result.get('inserted')} | qualified={result.get('qualified')} | "
                        f"super_priority={result.get('super_priority')}"
                    )
                await interaction.followup.send(message, ephemeral=True)
            except Exception as exc:
                await interaction.followup.send(f"Scan failed: {exc}", ephemeral=True)

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
            print("Discord bot disabled: DISCORD_BOT_TOKEN is not configured.")
            return
        if self._task and not self._task.done():
            return
        self._stopping = False
        print("Starting Discord bot client.")
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
