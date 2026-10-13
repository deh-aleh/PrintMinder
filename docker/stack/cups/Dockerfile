FROM debian:bookworm-slim
RUN apt-get update \
 && apt-get install -y --no-install-recommends cups cups-client cups-ipp-utils cups-filters cups-pdf ghostscript poppler-utils \
    printer-driver-brlaser printer-driver-gutenprint printer-driver-splix printer-driver-foo2zjs \
 && rm -rf /var/lib/apt/lists/*
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
