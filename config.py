"""Configuration module for Telegram Lab Traffic Generator.

Loads settings from Streamlit secrets (st.secrets) with fallback to
environment variables. Never hard-codes sensitive values.
"""

import os
import ipaddress
from typing import List, Optional


def _get_secret(key: str, default: Optional[str] = None) -> Optional[str]:
    """Retrieve a secret from Streamlit secrets or environment variables."""
    try:
        import streamlit as st
        value = st.secrets.get(key)
        if value is not None:
            return str(value)
    except Exception:
        pass
    return os.environ.get(key, default)


def get_telegram_token() -> str:
    """Return the Telegram bot token. Raises if not configured."""
    token = _get_secret("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN is not set. "
            "Add it to .streamlit/secrets.toml or set the environment variable."
        )
    return token


def get_authorized_user_ids() -> List[int]:
    """Return list of authorized Telegram user IDs."""
    raw = _get_secret("AUTHORIZED_TELEGRAM_USER_IDS", "")
    if not raw:
        return []
    try:
        return [int(uid.strip()) for uid in str(raw).split(",") if uid.strip()]
    except ValueError:
        return []


def get_max_duration() -> int:
    """Maximum test duration in seconds (default: 120)."""
    try:
        return int(_get_secret("MAX_DURATION", "120"))
    except (TypeError, ValueError):
        return 120


def get_max_rate() -> int:
    """Maximum packets/requests per second (default: 500)."""
    try:
        return int(_get_secret("MAX_RATE", "500"))
    except (TypeError, ValueError):
        return 500


# ---------- Validation helpers ----------

def validate_ip(ip_str: str) -> str:
    """Validate and return a sanitised IP string.

    Rules:
    * Must be a valid IPv4 or IPv6 address.
    * Must NOT be multicast (224.0.0.0/4, ff00::/8).
    * Must NOT be a broadcast address (255.255.255.255).

    Raises ValueError with a human-readable message on failure.
    """
    try:
        addr = ipaddress.ip_address(ip_str)
    except ValueError:
        raise ValueError(f"Invalid IP address: {ip_str}")

    if addr.is_multicast:
        raise ValueError(f"Multicast addresses are not allowed: {ip_str}")

    if ip_str == "255.255.255.255":
        raise ValueError("Broadcast address 255.255.255.255 is not allowed.")

    return str(addr)


def validate_port(port: int) -> int:
    if not (1 <= port <= 65535):
        raise ValueError(f"Port must be 1-65535, got {port}.")
    return port


def validate_duration(duration: int, max_dur: int) -> int:
    if duration < 1:
        raise ValueError("Duration must be at least 1 second.")
    if duration > max_dur:
        raise ValueError(f"Duration exceeds maximum ({max_dur}s).")
    return duration


def validate_rate(rate: int, max_rate: int) -> int:
    if rate < 1:
        raise ValueError("Rate must be at least 1 pps.")
    if rate > max_rate:
        raise ValueError(f"Rate exceeds maximum ({max_rate} pps).")
    return rate
