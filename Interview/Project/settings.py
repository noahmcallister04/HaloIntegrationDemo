"""Loads config.yaml, with environment-variable overrides for secrets."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent
CONFIG_PATH = Path(os.environ.get("SRT_CONFIG", PROJECT_ROOT / "config.yaml"))

_ENV_OVERRIDES = {
    "HALO_BASE_URL": ("halo", "base_url"),
    "HALO_AUTH_URL": ("halo", "auth_url"),
    "HALO_CLIENT_ID": ("halo", "client_id"),
    "HALO_CLIENT_SECRET": ("halo", "client_secret"),
    "HALO_TICKET_URL": ("halo", "ticket_url"),
    "WEBHOOK_SECRET": ("middleware", "webhook_secret"),
}


@lru_cache
def load_config() -> dict:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    for env_var, (section, key) in _ENV_OVERRIDES.items():
        if os.environ.get(env_var):
            cfg[section][key] = os.environ[env_var]
    return cfg


def resolve_path(path: str | Path) -> Path:
    """Resolves config paths relative to the project root."""
    p = Path(path)
    return p if p.is_absolute() else PROJECT_ROOT / p
