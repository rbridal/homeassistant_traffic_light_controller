"""Configuration loading."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


class ConfigError(Exception):
    pass


def load_config(path: str | Path) -> dict[str, Any]:
    path = Path(path)
    if not path.is_file():
        raise ConfigError(f"Config file not found: {path}")

    with path.open() as f:
        data = yaml.safe_load(f)

    if not isinstance(data, dict):
        raise ConfigError("Config root must be a mapping")

    # Basic validation
    required = ["mqtt", "i2c", "relays", "discovery"]
    for key in required:
        if key not in data:
            raise ConfigError(f"Missing required section: {key}")

    mqtt = data["mqtt"]
    for key in ("host", "port", "username", "password"):
        if key not in mqtt:
            raise ConfigError(f"mqtt.{key} is required")

    return data
