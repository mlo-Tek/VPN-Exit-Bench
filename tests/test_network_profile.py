import json
from types import SimpleNamespace

from network_profile import canonical_isp, enrich_public_info, parse_ipinfo_org


def test_parse_ipinfo_org():
    assert parse_ipinfo_org("AS9009 M247 Europe SRL") == ("AS9009", "M247 Europe SRL")
    assert parse_ipinfo_org("NForce Entertainment B.V.") == (None, "NForce Entertainment B.V.")
    assert parse_ipinfo_org("") == (None, None)


def test_crypto_storm_observed_isps_are_canonicalized():
    assert canonical_isp("AS9009", "M247 Europe SRL") == "M247"
    assert canonical_isp("UNITED COLO GmbH") == "UNITED COLO"
    assert canonical_isp("NForce Entertainment B.V.") == "NForce Entertainment"
    assert canonical_isp("AltusHost Inc.") == "AltusHost"
    assert canonical_isp("Private Layer INC") == "Private Layer"


def test_common_hosters_are_canonicalized():
    assert canonical_isp("AS24940 Hetzner Online GmbH") == "Hetzner"
    assert canonical_isp("OVH SAS") == "OVHcloud"
    assert canonical_isp("The Constant Company, LLC") == "Vultr"
    assert canonical_isp("DataCamp Limited") == "DataCamp / CDN77"


def test_enrich_public_info_adds_network_profile():
    def fake_run(cmd, timeout=30, check=False):
        joined = " ".join(cmd)
        if "network-info" in joined:
            return SimpleNamespace(
                returncode=0,
                stdout=json.dumps({"data": {"prefix": "37.120.217.0/24", "asns": [9009]}}),
                stderr="",
            )
        if cmd and cmd[0] == "dig":
            return SimpleNamespace(returncode=0, stdout="berlin.example.net.\n", stderr="")
        raise AssertionError(f"unexpected command: {cmd}")

    result = enrich_public_info(
        {
            "ip": "37.120.217.78",
            "city": "Berlin",
            "country": "DE",
            "org": "AS9009 M247 Europe SRL",
        },
        fake_run,
    )

    network = result["network"]
    assert network["asn"] == "AS9009"
    assert network["organization"] == "M247 Europe SRL"
    assert network["isp"] == "M247"
    assert network["hosting_provider"] == "M247"
    assert network["bgp_prefix"] == "37.120.217.0/24"
    assert network["rdns"] == "berlin.example.net"
    assert network["catalog_match"] is True
