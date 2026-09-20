from provider_identity import canonical_provider, infer_provider


def test_cryptostorm_is_inferred_from_root_config_name():
    assert canonical_provider("Other", name="cryptostorm-dusseldorf.conf") == "CryptoStorm"
    assert canonical_provider("Other", name="crypto-storm-netherlands.conf") == "CryptoStorm"


def test_cryptostorm_folder_is_canonicalized():
    assert canonical_provider("cryptostorm", name="dusseldorf.conf") == "CryptoStorm"
    assert canonical_provider("Other", name="dusseldorf.conf", rel="CryptoStorm/dusseldorf.conf") == "CryptoStorm"


def test_existing_known_providers_keep_their_canonical_names():
    assert infer_provider("proton-nl-907.conf") == "Proton"
    assert infer_provider("ovpn-de-fra94.conf") == "OVPN"
    assert infer_provider("AirVPN_NL-Alblasserdam_Piautos_UDP-1637-Entry3.ovpn") == "AirVPN"


def test_unknown_explicit_provider_is_preserved():
    assert canonical_provider("MyVPN", name="node.conf") == "MyVPN"
    assert canonical_provider("Other", name="node.conf") == "Other"
