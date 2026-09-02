import json
import os
import time
from pathlib import Path

from config_security import validate_config_path
from worker_v2 import main


def validate_runtime_config():
    kind = os.environ.get("VPN_TYPE", "auto").lower()
    if kind == "none":
        return True

    cfg = Path(os.environ.get("VPN_CONFIG", "/vpn/config"))
    if kind not in {"wireguard", "openvpn"}:
        kind = "openvpn" if cfg.suffix.lower() == ".ovpn" else "wireguard"

    error = validate_config_path(cfg, kind)
    if not error:
        return True

    now = int(time.time())
    print(
        json.dumps(
            {
                "ok": False,
                "config": cfg.name,
                "type": kind,
                "started_at": now,
                "finished_at": now,
                "duration_s": 0,
                "error": f"Unsichere VPN-Config abgelehnt: {error}",
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    return False


if __name__ == "__main__" and validate_runtime_config():
    main()
