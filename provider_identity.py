import re
from pathlib import Path

_GENERIC_PROVIDERS = {"", "other", "vpn", "unknown", "unbekannt"}

_PROVIDER_RULES = (
    (re.compile(r"(^|[-_. ])cryptostorm(?:$|[-_. ])|crypto[-_. ]*storm", re.I), "CryptoStorm"),
    (re.compile(r"(^|[-_. ])proton(?:$|[-_. ])", re.I), "Proton"),
    (re.compile(r"(^|[-_. ])ovpn(?:$|[-_. ])", re.I), "OVPN"),
    (re.compile(r"(^|[-_. ])mullvad(?:$|[-_. ])", re.I), "Mullvad"),
    (re.compile(r"(^|[-_. ])airvpn(?:$|[-_. ])", re.I), "AirVPN"),
    (re.compile(r"(^|[-_. ])ivpn(?:$|[-_. ])", re.I), "IVPN"),
    (re.compile(r"(^|[-_. ])windscribe(?:$|[-_. ])", re.I), "Windscribe"),
    (re.compile(r"(^|[-_. ])surfshark(?:$|[-_. ])", re.I), "Surfshark"),
    (re.compile(r"(^|[-_. ])nord(?:vpn)?(?:$|[-_. ])", re.I), "NordVPN"),
    (re.compile(r"(^|[-_. ])pia(?:$|[-_. ])|privateinternetaccess", re.I), "PIA"),
)


def infer_provider(value):
    """Infer a known VPN provider from a filename, folder or provider label."""
    text = str(value or "").strip()
    if not text:
        return "Other"

    # Drop .conf/.ovpn before matching so the OpenVPN extension itself cannot
    # accidentally be interpreted as the OVPN provider.
    text = Path(text).stem
    for pattern, provider in _PROVIDER_RULES:
        if pattern.search(text):
            return provider

    compact = re.sub(r"[^a-z0-9]+", "", text.lower())
    if "cryptostorm" in compact:
        return "CryptoStorm"
    return "Other"


def canonical_provider(provider=None, name=None, rel=None):
    """Return a stable display/storage provider without inventing unknown names.

    Existing explicit provider/folder names are preserved. Generic labels such
    as ``Other`` are upgraded when a known provider can be inferred from the
    config filename or relative path. This also repairs historical rows without
    rewriting the SQLite database.
    """
    explicit = str(provider or "").strip()
    if explicit and explicit.lower() not in _GENERIC_PROVIDERS:
        known = infer_provider(explicit)
        return known if known != "Other" else explicit

    rel_text = str(rel or "").strip()
    if rel_text:
        parts = Path(rel_text).parts
        if len(parts) > 1:
            folder = str(parts[0]).strip()
            if folder and folder.lower() not in _GENERIC_PROVIDERS:
                known = infer_provider(folder)
                return known if known != "Other" else folder

    for candidate in (name, rel_text):
        known = infer_provider(candidate)
        if known != "Other":
            return known

    return "Other"
