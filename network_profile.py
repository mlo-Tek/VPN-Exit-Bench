import json
import re


# Canonical ISP / datacenter names used only as display metadata. The benchmark
# score never depends on this catalog.
ISP_CATALOG = (
    {"name": "M247", "patterns": ("m247", "m247 europe"), "asns": ("AS9009",)},
    {"name": "UNITED COLO", "patterns": ("united colo",), "asns": ()},
    {"name": "NForce Entertainment", "patterns": ("nforce", "nforce entertainment"), "asns": ("AS43350",)},
    {"name": "AltusHost", "patterns": ("altushost",), "asns": ("AS51430",)},
    {"name": "Private Layer", "patterns": ("private layer",), "asns": ()},
    {"name": "DataCamp / CDN77", "patterns": ("datacamp", "data camp", "cdn77"), "asns": ("AS60068",)},
    {"name": "DataPacket", "patterns": ("datapacket", "data packet"), "asns": ()},
    {"name": "Leaseweb", "patterns": ("leaseweb",), "asns": ()},
    {"name": "Worldstream", "patterns": ("worldstream",), "asns": ()},
    {"name": "Clouvider", "patterns": ("clouvider",), "asns": ()},
    {"name": "Serverius", "patterns": ("serverius",), "asns": ()},
    {"name": "NovoServe", "patterns": ("novoserve",), "asns": ()},
    {"name": "Hetzner", "patterns": ("hetzner",), "asns": ("AS24940",)},
    {"name": "OVHcloud", "patterns": ("ovh", "ovhcloud"), "asns": ("AS16276",)},
    {"name": "Vultr", "patterns": ("vultr", "choopa", "the constant company"), "asns": ("AS20473",)},
    {"name": "DigitalOcean", "patterns": ("digitalocean", "digital ocean"), "asns": ("AS14061",)},
    {"name": "Akamai / Linode", "patterns": ("linode",), "asns": ("AS63949",)},
    {"name": "Gcore", "patterns": ("gcore", "g-core"), "asns": ()},
    {"name": "Hivelocity", "patterns": ("hivelocity",), "asns": ()},
    {"name": "Tzulo", "patterns": ("tzulo",), "asns": ()},
    {"name": "HostHatch", "patterns": ("hosthatch",), "asns": ()},
    {"name": "QuadraNet", "patterns": ("quadranet",), "asns": ()},
    {"name": "PacketHub", "patterns": ("packethub", "packet hub"), "asns": ()},
    {"name": "Psychz Networks", "patterns": ("psychz",), "asns": ()},
    {"name": "FDCservers", "patterns": ("fdcservers", "fdc servers"), "asns": ()},
    {"name": "netcup", "patterns": ("netcup",), "asns": ()},
    {"name": "Contabo", "patterns": ("contabo",), "asns": ()},
    {"name": "IONOS", "patterns": ("ionos", "1&1 internet", "1und1"), "asns": ()},
    {"name": "Cogent Communications", "patterns": ("cogent",), "asns": ("AS174",)},
    {"name": "GTT", "patterns": ("gtt communications",), "asns": ("AS3257",)},
    {"name": "RETN", "patterns": ("retn",), "asns": ("AS9002",)},
)


def parse_ipinfo_org(value):
    text = str(value or "").strip()
    if not text:
        return None, None
    match = re.match(r"^(AS\d+)\s+(.+)$", text, flags=re.I)
    if match:
        return match.group(1).upper(), match.group(2).strip()
    return None, text


def _normalize(value):
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def canonical_isp(*values):
    text = " ".join(_normalize(value) for value in values if value)
    asns = {match.upper() for match in re.findall(r"\bAS\d+\b", " ".join(str(v or "") for v in values), flags=re.I)}
    for item in ISP_CATALOG:
        if asns.intersection(item["asns"]):
            return item["name"]
        if any(pattern in text for pattern in item["patterns"]):
            return item["name"]
    return None


def _curl_json(run, url, timeout=6):
    try:
        proc = run(["curl", "-4", "-fsS", "--max-time", str(timeout), url], timeout=timeout + 3)
    except Exception:
        return None
    if proc.returncode != 0:
        return None
    try:
        return json.loads(proc.stdout)
    except Exception:
        return None


def _ripe_network(run, ip):
    payload = _curl_json(
        run,
        f"https://stat.ripe.net/data/network-info/data.json?resource={ip}",
        timeout=6,
    )
    data = (payload or {}).get("data") or {}
    prefix = data.get("prefix")
    asns = data.get("asns") or []
    asn = None
    if asns:
        first = str(asns[0]).upper()
        asn = first if first.startswith("AS") else f"AS{first}"
    return asn, prefix


def _ripe_holder(run, asn):
    if not asn:
        return None
    payload = _curl_json(
        run,
        f"https://stat.ripe.net/data/as-overview/data.json?resource={asn}",
        timeout=6,
    )
    holder = ((payload or {}).get("data") or {}).get("holder")
    return str(holder).strip() if holder else None


def _reverse_dns(run, ip):
    try:
        proc = run(["dig", "-x", ip, "+short"], timeout=5)
    except Exception:
        return None
    if proc.returncode != 0:
        return None
    names = [line.strip().rstrip(".") for line in proc.stdout.splitlines() if line.strip()]
    return names[0] if names else None


def enrich_public_info(info, run):
    out = dict(info or {})
    ip = out.get("ip")
    if not ip:
        return out

    ipinfo_asn, ipinfo_org = parse_ipinfo_org(out.get("org"))
    ripe_asn, prefix = _ripe_network(run, ip)
    asn = ipinfo_asn or ripe_asn
    organization = ipinfo_org or _ripe_holder(run, asn)
    rdns = _reverse_dns(run, ip)

    catalog_name = canonical_isp(asn, organization, out.get("org"), rdns)
    isp = catalog_name or organization

    out["network"] = {
        "asn": asn,
        "organization": organization,
        "isp": isp,
        "hosting_provider": catalog_name,
        "bgp_prefix": prefix,
        "rdns": rdns,
        "catalog_match": bool(catalog_name),
    }
    return out
