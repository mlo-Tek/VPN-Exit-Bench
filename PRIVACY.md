# Privacy

VPN Exit Bench is intended to run locally on the user's own Unraid server. The project does not include analytics, advertising, telemetry, or a service operated by the maintainer that receives benchmark results.

## Data stored locally

Persistent data is stored under `/config`, normally backed by `/mnt/cache/appdata/vpn-exit-bench` on Unraid.

This can include:

- uploaded WireGuard/OpenVPN configuration files
- benchmark history in `results.db`
- VPN exit IP, city/country and network/provider information returned by public IP-information services
- throughput, latency, jitter, packet-loss and port-forwarding measurements
- the direct-line baseline throughput

VPN configurations can contain private keys, certificates or credentials. They remain in the user's local appdata storage and are mounted read-only into the selected short-lived benchmark worker.

## Direct public IP

The application must temporarily determine the public IP before connecting a VPN so it can verify that the egress address changed.

Current versions:

- use the pre-VPN public IP only in worker memory for that verification;
- do not persist it in benchmark results;
- do not expose it in the browser job API;
- scrub this field from results written by older versions when the application starts;
- do not persist the direct public IP as part of a baseline result.

The direct public IP is still visible to the external service contacted to determine it. This is inherent to making that request.

## External services

A benchmark deliberately contacts third-party network endpoints. Depending on the test, these can include:

- public-IP / IP-information services such as ipinfo.io and api.ipify.org
- Cloudflare and Google ICMP targets
- Leaseweb speed-test endpoints
- public European iPerf3/datacenter endpoints used for peer-connectivity measurements
- the external port-check service used for incoming-port verification
- the configured VPN provider endpoint itself

Those services can see the source IP used for their request. During a VPN test this should normally be the VPN exit IP. During direct/baseline measurements it is the user's normal public internet address.

VPN Exit Bench does not control the privacy policies or logging practices of those third-party services.

## Data sent to the maintainer

The application does not automatically send the following to `mlo-Tek`:

- VPN configs
- private keys
- benchmark history
- IP addresses
- usage analytics

If a user voluntarily posts logs, screenshots or database contents to GitHub, those items are shared by the user and may contain identifying network information. Review diagnostic material before posting it publicly.

## Deletion

VPN configs and benchmark results can be deleted from the WebUI. Users can also remove the persistent appdata directory themselves when the application is stopped.

Deleting the Docker container alone does not remove data stored in the mapped appdata directory.

## Network exposure

The WebUI should be kept on a trusted LAN/management network. Do not expose port `8787` directly to the public internet.
