FROM python:3.12-slim
# The image does not know the host user: docker-compose.yml starts it with `user: PUID:PGID`, so the bind-mounted
# TLS key (mode 600) is readable. /data is world-writable (sticky) so a new volume works for whichever user that is.
RUN groupadd -g 1000 gateway && useradd -u 1000 -g 1000 -M -s /usr/sbin/nologin gateway \
 && mkdir /data && chmod 1777 /data
WORKDIR /src
COPY pyproject.toml LICENSE NOTICE ./
COPY app ./app
RUN pip install --no-cache-dir . && cd / && rm -rf /src
USER gateway
ENV CUPSPL_HOST=0.0.0.0 CUPSPL_PORT=8631 \
    CUPSPL_CUPS_URL=unix:///run/cups/cups.sock \
    CUPSPL_SCAN_URL=http://ipp-usb:60000 \
    CUPSPL_DATABASE_URL=sqlite:////data/gateway.db \
    CUPSPL_TLS_CERTFILE=/tls/fullchain.pem CUPSPL_TLS_KEYFILE=/tls/privkey.pem
VOLUME /data
EXPOSE 8631
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s \
  CMD python -c "import ssl,urllib.request as u; c=ssl.create_default_context(); c.check_hostname=False; c.verify_mode=ssl.CERT_NONE; u.urlopen('https://127.0.0.1:8631/healthz', context=c, timeout=4)" || exit 1
CMD ["cups-policy-gateway"]
