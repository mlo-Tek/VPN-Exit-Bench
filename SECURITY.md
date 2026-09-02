# Security Policy

VPN Exit Bench handles VPN configuration files and can communicate with a Docker daemon. Treat security reports seriously and avoid publishing sensitive exploit details or credentials.

## Supported versions

The project is currently under active development. Security fixes are provided for the latest code on `main` and the current `ghcr.io/mlo-tek/vpn-exit-bench:latest` image.

Older images and historical commits are not maintained as separate supported release lines.

## Reporting a vulnerability

**Do not open a public GitHub issue containing exploit details, private keys, VPN configs, credentials, tokens, private IP information, or other sensitive data.**

Preferred reporting method:

1. Use GitHub's private vulnerability reporting / Security Advisory flow for this repository when available:
   `https://github.com/mlo-Tek/VPN-Exit-Bench/security/advisories/new`
2. If private reporting is not available, contact the maintainer through the GitHub profile at `https://github.com/mlo-Tek` and request a private channel before sending technical details.

Include, where possible:

- affected version or commit
- impact and attack prerequisites
- minimal reproduction steps
- whether credentials, VPN private keys, host access, or Docker access may be exposed
- suggested mitigation if known

Do not include real production secrets in a proof of concept.

## High-impact areas

Reports involving the following are especially important:

- access to `/var/run/docker.sock` or a Docker Socket Proxy
- arbitrary command execution through WireGuard/OpenVPN configs
- authentication or CSRF bypass
- path traversal or unintended config-file access
- exposure of VPN private keys, certificates, credentials, or the user's direct public IP
- container escape or privilege escalation from benchmark workers
- unsafe Docker API permissions
- persistent cross-site scripting or other browser-to-host attack paths
- supply-chain compromise of the published GHCR image or GitHub Actions workflows

## Security model

VPN Exit Bench is intended for a trusted LAN or management network. It is **not designed to be exposed directly to the public internet**.

The main application may require privileged Docker API operations to create short-lived benchmark workers. The recommended deployment uses a restricted Docker Socket Proxy rather than mounting the Docker socket directly.

Benchmark workers receive only the capabilities and devices required for VPN networking and do not receive the Docker socket.

## Credentials and leaked secrets

If you believe a real VPN private key, certificate private key, password, API token, or other credential has been exposed:

1. revoke/rotate it with the provider immediately;
2. do not paste it into an issue or discussion;
3. report where it appeared and which commit/artifact contained it.

Removing a secret from the current branch does not remove it from Git history. Exposed secrets must still be rotated.

## Disclosure

Please allow reasonable time for investigation and a fix before public disclosure. This is a community-maintained, vibe-coded project and does not currently have a guaranteed security-response SLA.
