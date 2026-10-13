FROM debian:bookworm-slim
RUN apt-get update \
 && apt-get install -y --no-install-recommends ipp-usb usbutils curl \
 && rm -rf /var/lib/apt/lists/*
COPY ipp-usb.conf /etc/ipp-usb/ipp-usb.conf
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
EXPOSE 60000-60099
ENTRYPOINT ["/entrypoint.sh"]
