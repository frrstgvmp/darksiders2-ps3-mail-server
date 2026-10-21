FROM debian:13-slim

RUN apt-get update \
    && apt-get install --no-install-recommends -y python3 python3-cryptography ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 ds2 \
    && useradd --uid 10001 --gid ds2 --no-create-home ds2

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HOME=/tmp
WORKDIR /app
COPY VERSION LICENSE NOTICE ds2_server.py http_server.py cloud_api.py dns_probe.py \
     access_control.py psn_auth.py service_limits.py news_api.py \
     generate_server_certificates.py backup_database.py docker_entrypoint.py ./
COPY assets/ ./assets/
COPY deployment/config.public.example.json ./config.example.json
LABEL org.opencontainers.image.title="Darksiders II PS3 Mail Server" \
      org.opencontainers.image.source="https://github.com/frrstgvmp/darksiders2-ps3-mail-server" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.version="0.5.0"
USER 10001:10001
EXPOSE 53/tcp 53/udp 443/tcp 8443/tcp
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD ["python3", "/app/docker_entrypoint.py", "health"]
ENTRYPOINT ["python3", "/app/docker_entrypoint.py"]
CMD ["serve"]
