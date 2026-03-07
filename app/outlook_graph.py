from __future__ import annotations

from pathlib import Path
from typing import Tuple

from msal import PublicClientApplication, SerializableTokenCache

from app.config import settings


def _authority() -> str:
    tenant = settings.outlook_tenant or "consumers"
    return f"https://login.microsoftonline.com/{tenant}"


def _load_cache(path: Path) -> SerializableTokenCache:
    cache = SerializableTokenCache()
    if path.exists():
        cache.deserialize(path.read_text(encoding="utf-8"))
    return cache


def _save_cache(cache: SerializableTokenCache, path: Path) -> None:
    if cache.has_state_changed:
        path.write_text(cache.serialize(), encoding="utf-8")


def _build_client(cache: SerializableTokenCache) -> PublicClientApplication:
    return PublicClientApplication(
        client_id=settings.outlook_client_id,
        authority=_authority(),
        token_cache=cache,
    )


def acquire_access_token_silent() -> Tuple[str | None, str | None]:
    if not settings.outlook_client_id:
        return None, "OUTLOOK_CLIENT_ID is missing in .env."

    cache_path = settings.outlook_cache_path
    cache = _load_cache(cache_path)
    app = _build_client(cache)
    accounts = app.get_accounts()
    if not accounts:
        return None, "No Outlook token cache found. Run scripts/setup_outlook_graph_auth.py first."

    result = app.acquire_token_silent(settings.outlook_scope_list, account=accounts[0])
    _save_cache(cache, cache_path)

    if not result:
        return None, "Silent token refresh failed. Run scripts/setup_outlook_graph_auth.py again."
    token = result.get("access_token")
    if token:
        return token, None
    return None, result.get("error_description") or "Unable to acquire Outlook Graph access token."


def run_device_code_login() -> Tuple[bool, str]:
    if not settings.outlook_client_id:
        return False, "OUTLOOK_CLIENT_ID is missing in .env."

    cache_path = settings.outlook_cache_path
    cache = _load_cache(cache_path)
    app = _build_client(cache)
    flow = app.initiate_device_flow(scopes=settings.outlook_scope_list)
    if "user_code" not in flow:
        return False, f"Device flow failed to initialize: {flow}"

    print(flow.get("message", "Open the shown URL and enter the code to sign in."))
    result = app.acquire_token_by_device_flow(flow)
    _save_cache(cache, cache_path)

    if "access_token" in result:
        return True, "Outlook OAuth completed and token cache saved."
    return False, result.get("error_description") or f"Outlook OAuth failed: {result}"
