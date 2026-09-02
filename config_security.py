from pathlib import Path

MAX_CONFIG_BYTES = 512 * 1024
ALLOWED_CONFIG_SUFFIXES = {".conf", ".ovpn"}

# wg-quick can execute these values through /bin/sh.
WG_EXEC_DIRECTIVES = {"preup", "postup", "predown", "postdown"}

# OpenVPN directives that can execute external code or expose a management
# control surface. Provider configs are treated as data, not executable input.
OPENVPN_EXEC_DIRECTIVES = {
    "script-security",
    "up",
    "down",
    "route-up",
    "route-pre-down",
    "ipchange",
    "learn-address",
    "client-connect",
    "client-disconnect",
    "auth-user-pass-verify",
    "tls-verify",
    "plugin",
    "management",
    "management-client",
    "management-external-key",
    "management-external-cert",
}


def validate_config_bytes(raw, suffix):
    """Return None when a VPN config is safe enough to execute, else an error.

    This is deliberately conservative. VPN Exit Bench only needs normal client
    tunnel configuration; script/plugin/management hooks are unnecessary and
    materially increase the attack surface of a benchmark worker.
    """
    suffix = str(suffix or "").lower()
    if suffix not in ALLOWED_CONFIG_SUFFIXES:
        return "Nur .conf und .ovpn sind erlaubt."
    if len(raw) > MAX_CONFIG_BYTES:
        return "Config ist größer als 512 KiB."
    if not raw.strip():
        return "Config ist leer."
    if b"\x00" in raw:
        return "Binärdateien werden nicht akzeptiert."

    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        return "Config ist keine gültige UTF-8-Textdatei."

    if suffix == ".conf":
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key = stripped.split("=", 1)[0].strip().lower()
            if key in WG_EXEC_DIRECTIVES:
                return f"Unsichere WireGuard-Direktive blockiert: {key}."

    if suffix == ".ovpn":
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith(("#", ";", "<")):
                continue
            directive = stripped.split(None, 1)[0].lower()
            if directive in OPENVPN_EXEC_DIRECTIVES:
                return f"Unsichere OpenVPN-Direktive blockiert: {directive}."

    return None


def validate_config_path(path, vpn_type=None):
    """Validate a config immediately before a worker executes it."""
    path = Path(path)
    try:
        raw = path.read_bytes()
    except OSError as exc:
        return f"Config kann nicht gelesen werden: {exc}"

    kind = str(vpn_type or "").lower()
    if kind == "openvpn":
        suffix = ".ovpn"
    elif kind == "wireguard":
        suffix = ".conf"
    else:
        suffix = path.suffix.lower()
    return validate_config_bytes(raw, suffix)
