from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv
from supabase import Client, create_client


ENV_FILE = Path(__file__).resolve().parent / ".env"


@dataclass(frozen=True)
class MobileCloudSettings:
    url: str
    anon_key: str
    mobile_pin: str
    tech_manager_pin: str = ""


def load_mobile_cloud_settings() -> MobileCloudSettings:
    load_dotenv(ENV_FILE)
    return MobileCloudSettings(
        url=os.getenv("SUPABASE_URL", "").strip(),
        anon_key=os.getenv("SUPABASE_ANON_KEY", "").strip(),
        mobile_pin=os.getenv("MOBILE_PIN", "").strip(),
        tech_manager_pin=os.getenv("TECH_MANAGER_PIN", "").strip() or os.getenv("MOULD_MANAGER_PIN", "").strip(),
    )


def validate_mobile_cloud_settings(settings: MobileCloudSettings) -> None:
    missing = []
    if not settings.url:
        missing.append("SUPABASE_URL")
    if not settings.anon_key:
        missing.append("SUPABASE_ANON_KEY")
    if not settings.mobile_pin:
        missing.append("MOBILE_PIN")
    if missing:
        raise RuntimeError(f"Missing environment settings: {', '.join(missing)}")


def mobile_cloud_client(settings: MobileCloudSettings) -> Client:
    validate_mobile_cloud_settings(settings)
    return create_client(settings.url, settings.anon_key)
