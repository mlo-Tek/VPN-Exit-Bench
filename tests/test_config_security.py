from pathlib import Path

from config_security import MAX_CONFIG_BYTES, validate_config_bytes, validate_config_path


def test_safe_wireguard_config_is_accepted(tmp_path):
    raw = b"""[Interface]\nPrivateKey = TEST_VALUE\nAddress = 10.0.0.2/32\n\n[Peer]\nPublicKey = TEST_PUBLIC_VALUE\nEndpoint = vpn.example.invalid:51820\nAllowedIPs = 0.0.0.0/0\n"""
    assert validate_config_bytes(raw, ".conf") is None

    path = tmp_path / "test.conf"
    path.write_bytes(raw)
    assert validate_config_path(path, "wireguard") is None


def test_wireguard_shell_hook_is_rejected():
    raw = b"[Interface]\nPrivateKey = TEST_VALUE\nPostUp = touch /tmp/should-not-run\n"
    error = validate_config_bytes(raw, ".conf")
    assert error is not None
    assert "postup" in error.lower()


def test_openvpn_plugin_and_management_are_rejected():
    plugin = b"client\ndev tun\nplugin /tmp/untrusted.so\n"
    management = b"client\ndev tun\nmanagement 0.0.0.0 7505\n"
    assert "plugin" in validate_config_bytes(plugin, ".ovpn").lower()
    assert "management" in validate_config_bytes(management, ".ovpn").lower()


def test_binary_and_oversized_configs_are_rejected():
    assert validate_config_bytes(b"abc\x00def", ".conf") is not None
    assert validate_config_bytes(b"a" * (MAX_CONFIG_BYTES + 1), ".conf") is not None


def test_type_controls_validation_when_path_has_no_suffix(tmp_path):
    path = Path(tmp_path) / "config"
    path.write_bytes(b"client\ndev tun\nup /tmp/script\n")
    error = validate_config_path(path, "openvpn")
    assert error is not None
    assert "up" in error.lower()
