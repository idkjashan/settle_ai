"""Network utilities for zero-subshell host auto-discovery and WSL2 routing."""

from __future__ import annotations

import logging
import socket
import struct
from typing import Optional
from urllib.parse import urlsplit

logger = logging.getLogger(__name__)

_RESOLVED_GATEWAY_CACHE: Optional[str] = None
_RESOLVED_OLLAMA_URL_CACHE: dict[str, str] = {}


def resolve_wsl2_gateway() -> Optional[str]:
    """Auto-discover WSL2 host gateway IP via /proc/net/route in < 0.1ms using stdlib."""
    global _RESOLVED_GATEWAY_CACHE
    if _RESOLVED_GATEWAY_CACHE is not None:
        return _RESOLVED_GATEWAY_CACHE

    try:
        with open("/proc/net/route", "r", encoding="utf-8") as f:
            for line in f.readlines()[1:]:
                fields = line.strip().split()
                if len(fields) >= 3 and fields[1] == "00000000":
                    gw_hex = fields[2]
                    ip = socket.inet_ntoa(struct.pack("<L", int(gw_hex, 16)))
                    _RESOLVED_GATEWAY_CACHE = ip
                    logger.debug("Discovered WSL2 host gateway IP: %s", ip)
                    return ip
    except Exception as exc:
        logger.debug("Could not read /proc/net/route: %s", exc)

    return None


def is_port_open(host: str, port: int, timeout_sec: float = 0.25) -> bool:
    """Test TCP socket reachability for host:port with a fast timeout."""
    try:
        with socket.create_connection((host, port), timeout=timeout_sec):
            return True
    except (socket.timeout, OSError):
        return False


def resolve_ollama_url(configured_url: str, force_refresh: bool = False) -> str:
    """Resolve an Ollama base URL, testing localhost and auto-switching to WSL2 host gateway if needed."""
    global _RESOLVED_OLLAMA_URL_CACHE
    if not force_refresh and configured_url in _RESOLVED_OLLAMA_URL_CACHE:
        return _RESOLVED_OLLAMA_URL_CACHE[configured_url]

    try:
        parsed = urlsplit(configured_url)
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or 11434
        scheme = parsed.scheme or "http"

        if host in ("localhost", "127.0.0.1"):
            # Check if localhost itself is reachable
            if is_port_open(host, port, timeout_sec=0.2):
                _RESOLVED_OLLAMA_URL_CACHE[configured_url] = configured_url
                return configured_url

            # Unreachable on localhost: check WSL2 gateway
            gw = resolve_wsl2_gateway()
            if gw and is_port_open(gw, port, timeout_sec=0.25):
                candidate_url = f"{scheme}://{gw}:{port}"
                logger.info("Auto-resolved Ollama endpoint to WSL2 host: %s", candidate_url)
                _RESOLVED_OLLAMA_URL_CACHE[configured_url] = candidate_url
                return candidate_url
    except Exception as exc:
        logger.warning("Error resolving Ollama URL (%s): %s", configured_url, exc)

    _RESOLVED_OLLAMA_URL_CACHE[configured_url] = configured_url
    return configured_url
