"""
LLM provider settings, stored in a local file next to the project.

Three providers:
- zyt_foundry           ZYT Foundry (OpenAI-compatible), model fixed to gpt-6.1-sol. Default.
- openai_compatible     any OpenAI-compatible endpoint (base URL, key, model)
- anthropic_compatible  any Anthropic-compatible endpoint (base URL, key, model)

Environment variables seed the defaults; values saved from the settings page win.
  ZYT_FOUNDRY_API_KEY, ZYT_FOUNDRY_BASE_URL
  NEURALFORGE_HOME      folder for settings.json (default: <project>/.neuralforge)
"""

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SETTINGS_DIR = Path(os.environ.get("NEURALFORGE_HOME", str(PROJECT_ROOT / ".neuralforge")))
SETTINGS_PATH = SETTINGS_DIR / "settings.json"

ZYT_FOUNDRY_MODEL = "gpt-6.1-sol"
ZYT_FOUNDRY_DEFAULT_URL = "https://foundry.zyt.app/v1"

PROVIDERS = {
    "zyt_foundry": {
        "label": "ZYT Foundry",
        "kind": "openai",
        "base_url": None,           # from ZYT_FOUNDRY_BASE_URL or the default
        "model": ZYT_FOUNDRY_MODEL,
        "fixed_model": True,
        "fixed_url": True,
    },
    "openai_compatible": {
        "label": "OpenAI-compatible",
        "kind": "openai",
        "base_url": "https://api.openai.com/v1",
        "model": "",
        "fixed_model": False,
        "fixed_url": False,
    },
    "anthropic_compatible": {
        "label": "Anthropic-compatible",
        "kind": "anthropic",
        "base_url": "https://api.anthropic.com",
        "model": "claude-opus-5-5",
        "fixed_model": False,
        "fixed_url": False,
    },
}
DEFAULT_PROVIDER = "zyt_foundry"


@dataclass
class ProviderConfig:
    provider: str
    label: str
    kind: str           # "openai" or "anthropic"
    base_url: str
    model: str
    api_key: str


def _read() -> dict:
    try:
        with open(SETTINGS_PATH) as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _write(data: dict):
    SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=SETTINGS_DIR, prefix=".settings-", suffix=".json")
    with os.fdopen(fd, "w") as f:
        json.dump(data, f, indent=2)
    os.chmod(tmp, 0o600)
    os.replace(tmp, SETTINGS_PATH)


def _env_key(provider: str) -> str:
    return os.environ.get("ZYT_FOUNDRY_API_KEY", "") if provider == "zyt_foundry" else ""


def _resolve(provider: str, saved: dict) -> ProviderConfig:
    spec = PROVIDERS[provider]
    entry = saved.get("providers", {}).get(provider, {})
    if provider == "zyt_foundry":
        base_url = os.environ.get("ZYT_FOUNDRY_BASE_URL", ZYT_FOUNDRY_DEFAULT_URL)
    else:
        base_url = entry.get("base_url") or spec["base_url"]
    model = spec["model"] if spec["fixed_model"] else (entry.get("model") or spec["model"])
    return ProviderConfig(
        provider=provider,
        label=spec["label"],
        kind=spec["kind"],
        base_url=base_url.rstrip("/"),
        model=model,
        api_key=entry.get("api_key") or _env_key(provider),
    )


def active_config() -> ProviderConfig:
    saved = _read()
    provider = saved.get("active_provider", DEFAULT_PROVIDER)
    if provider not in PROVIDERS:
        provider = DEFAULT_PROVIDER
    return _resolve(provider, saved)


def _key_hint(key: str) -> str:
    return f"…{key[-4:]}" if len(key) >= 8 else ("set" if key else "")


def public_view() -> dict:
    """Settings for the UI. API keys are never returned, only whether one is set."""
    saved = _read()
    active = active_config().provider
    providers = {}
    for provider, spec in PROVIDERS.items():
        config = _resolve(provider, saved)
        entry = saved.get("providers", {}).get(provider, {})
        providers[provider] = {
            "label": spec["label"],
            "kind": spec["kind"],
            "base_url": config.base_url,
            "model": config.model,
            "fixed_model": spec["fixed_model"],
            "fixed_url": spec["fixed_url"],
            "has_key": bool(config.api_key),
            "key_hint": _key_hint(config.api_key),
            "key_source": "settings" if entry.get("api_key") else ("environment" if config.api_key else None),
        }
    return {
        "active_provider": active,
        "configured": providers[active]["has_key"] and bool(providers[active]["model"]),
        "providers": providers,
        "settings_path": str(SETTINGS_PATH),
    }


def _valid_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def update(changes: dict) -> dict:
    """Apply changes from the settings page.

    `changes` = {"active_provider": str?, "providers": {id: {"api_key"?, "base_url"?, "model"?, "clear_key"?}}}.
    An omitted or empty api_key keeps the stored one; clear_key removes it.
    Raises ValueError on bad input.
    """
    saved = _read()
    providers = saved.setdefault("providers", {})

    active = changes.get("active_provider")
    if active is not None:
        if active not in PROVIDERS:
            raise ValueError(f"Unknown provider {active!r}")
        saved["active_provider"] = active

    for provider, fields in (changes.get("providers") or {}).items():
        if provider not in PROVIDERS:
            raise ValueError(f"Unknown provider {provider!r}")
        spec = PROVIDERS[provider]
        entry = providers.setdefault(provider, {})
        if fields.get("clear_key"):
            entry.pop("api_key", None)
        key = (fields.get("api_key") or "").strip()
        if key:
            entry["api_key"] = key
        if "base_url" in fields and not spec["fixed_url"]:
            url = (fields.get("base_url") or "").strip()
            if url and not _valid_url(url):
                raise ValueError(f"Base URL must start with http:// or https://, got {url!r}")
            entry["base_url"] = url
        if "model" in fields and not spec["fixed_model"]:
            entry["model"] = (fields.get("model") or "").strip()

    _write(saved)
    return public_view()
