FROM python:3.11-slim

# Corporate TLS-inspection root CAs (e.g. Zscaler) — required so curl/pip can
# verify HTTPS certs when building behind a corporate proxy. Harmless no-op
# on networks without TLS inspection (folder is simply empty then).
COPY corporate-certs/*.crt /usr/local/share/ca-certificates/
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates && \
    update-ca-certificates && \
    rm -rf /var/lib/apt/lists/*

# Point pip/requests/urllib3 at the system CA bundle (which now includes the
# corporate certs above) instead of the certifi-bundled CAs, so HTTPS calls
# from pip, and from the agent's own outbound requests (Azure OpenAI, Teams,
# Slack), succeed behind a TLS-inspecting corporate proxy.
ENV SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt \
    REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt \
    PIP_CERT=/etc/ssl/certs/ca-certificates.crt

# Install kubectl
RUN apt-get update && apt-get install -y curl ca-certificates && \
    curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl" && \
    install -o root -g root -m 0755 kubectl /usr/local/bin/kubectl && \
    apt-get remove -y curl && apt-get autoremove -y && rm -rf /var/lib/apt/lists/* kubectl

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Drop root — run as non-root user
RUN useradd -m -u 1000 agent
USER agent

CMD ["python", "test_step1_monitoring.py"]
