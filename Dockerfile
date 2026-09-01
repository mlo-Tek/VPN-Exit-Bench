FROM python:3.12-alpine
RUN apk add --no-cache bash curl iproute2 iputils wireguard-tools openvpn jq ca-certificates bind-tools
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV PYTHONUNBUFFERED=1
EXPOSE 8787
CMD ["python", "app.py"]
