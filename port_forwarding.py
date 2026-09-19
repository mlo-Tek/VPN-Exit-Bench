def normalize_manual_forward_result(result, forwarded_port):
    """Normalize a manual port-forward check without overclaiming "closed".

    The generic external checker probes the caller's current public exit IP.
    Some VPN providers expose forwarded ports on a different ingress IP, so a
    negative probe against the exit IP does not prove that the provider-side
    forwarding rule is absent or closed.
    """
    normalized = dict(result or {})
    try:
        port = int(forwarded_port or 0)
    except (TypeError, ValueError):
        port = 0

    if port <= 0:
        return normalized

    normalized["configured"] = True
    normalized["public_port"] = port
    normalized["verification_scope"] = "current_exit_ip"

    if normalized.get("status") == "open":
        normalized["note"] = "Manual forwarded port was externally confirmed on the current VPN exit IP."
        return normalized

    original_verified = bool(normalized.get("verified"))
    original_tcp_open = normalized.get("tcp_open")
    normalized["exit_ip_check_verified"] = original_verified
    normalized["exit_ip_tcp_open"] = original_tcp_open

    # A manual forwarding rule is configured, but the current exit IP did not
    # prove external reachability. Providers may use a separate ingress IP for
    # forwarding, so report this as configured/unverified rather than closed.
    normalized["status"] = "mapped_unverified"
    normalized["verified"] = False
    normalized["tcp_open"] = None

    if original_verified and original_tcp_open is False:
        normalized["note"] = (
            "Forwarded port is configured, but the current VPN exit IP did not accept the external probe. "
            "Some VPN providers use a separate ingress IP for port forwarding, so this is not proof that the provider-side rule is closed."
        )
    else:
        normalized["note"] = (
            "Forwarded port is configured, but external reachability could not be confirmed on the current VPN exit IP."
        )
    return normalized
