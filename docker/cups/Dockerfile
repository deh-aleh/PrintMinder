FROM debian:bookworm-slim
RUN apt-get update \
 && apt-get install -y --no-install-recommends cups cups-client cups-pdf cups-filters ghostscript \
 && rm -rf /var/lib/apt/lists/*
COPY cupsd.conf /etc/cups/cupsd.conf
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
EXPOSE 631
ENTRYPOINT ["/entrypoint.sh"]
