FROM python:3.12-alpine

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

ENV PYTHONUNBUFFERED=1
EXPOSE 8787

CMD ["gunicorn", "--bind", "0.0.0.0:8787", "--workers", "1", "--threads", "8", "--timeout", "120", "app:app"]
