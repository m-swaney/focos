"""Config schema (pydantic models), validation, templates, and migrations for <home>/config/*.yml."""
from __future__ import annotations

CONFIG_VERSION = 3

# validation order
CONFIG_FILES = ("focos.yml", "profile.yml", "goals.yml", "accounts.yml", "entities.yml", "transfer_rules.yml",
                "sandbox_rules.yml", "analytics.yml", "properties.yml")
