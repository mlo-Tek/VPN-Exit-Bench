# Contributing

Contributions are welcome. VPN Exit Bench is an Unraid-native project and is intentionally maintained without Docker Compose instructions.

## Before contributing

Read:

- `README.md`
- `SECURITY.md`
- `PRIVACY.md`

The project was developed primarily with AI-assisted / vibe coding. Changes should therefore be reviewed as code, not accepted merely because generated output looks plausible.

## Security first

Never commit or attach real:

- WireGuard `.conf` files
- OpenVPN `.ovpn` files
- `PrivateKey` / `PresharedKey` values
- certificate private keys
- provider credentials
- API tokens
- `.env` files
- `results.db`

Use synthetic/example values in tests and documentation.

Security vulnerabilities should be reported using the private process in `SECURITY.md`, not as a public issue containing exploit details.

## Development checks

At minimum, run the equivalent of:

```bash
python -m py_compile app.py server.py worker.py worker_v2.py peer_scoring.py config_security.py
```

and build the image:

```bash
docker build -t vpn-exit-bench:test .
```

GitHub Actions additionally runs dependency auditing, static security analysis, CodeQL, Trivy scans and dependency review.

## Pull requests

Keep pull requests focused and explain:

- what changed
- why it changed
- security/privacy implications
- how it was tested
- whether existing Unraid installations remain compatible

Changes to benchmark targets or scoring should explain the measurement rationale because they can alter historical comparisons.

## Unraid compatibility

Do not make Docker Compose a required installation path. The supported deployment target is Unraid's native Docker/Community Applications workflow and XML templates.

When adding environment variables or mounts, update the Unraid template and README together.

## Dependencies and GitHub Actions

Prefer minimal dependencies. GitHub Actions must be pinned to a full commit SHA in workflows; Dependabot can then propose controlled updates.

## Generated code

AI-generated changes are allowed, but the contributor remains responsible for reviewing them for correctness, licensing, security, privacy and unintended behavior.
