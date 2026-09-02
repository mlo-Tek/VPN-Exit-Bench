FROM python:3.12.14-alpine3.24

LABEL org.opencontainers.image.source="https://github.com/mlo-Tek/VPN-Exit-Bench" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.title="VPN Exit Bench"

RUN apk add --no-cache \
    bash \
    bind-tools \
    ca-certificates \
    curl \
    iperf3 \
    iproute2 \
    iptables \
    iputils \
    jq \
    libnatpmp \
    nftables \
    openresolv \
    openvpn \
    wireguard-tools

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN python -m py_compile app.py server.py worker.py worker_v2.py peer_scoring.py config_security.py

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

EXPOSE 8787
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8787/api/health || exit 1

CMD ["gunicorn", "--bind", "0.0.0.0:8787", "--workers", "1", "--threads", "8", "--timeout", "120", "server:app"]
