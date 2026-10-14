from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # only real environment variables: a .env here belongs to docker compose, not to the app
    model_config = SettingsConfigDict(env_prefix="CUPSPL_", extra="ignore")

    database_url: str = "sqlite:///./cupspl.db"
    # CUPS is a private backend; the gateway owns :631. "unix:///run/cups/cups.sock" is the recommended form.
    cups_url: str = "unix:///run/cups/cups.sock"
    log_level: str = "INFO"
    # How often the same notice (same kind, same source) is reported again, in seconds. 0 = decided by log_level:
    # DEBUG 1 minute, INFO 1 day, WARNING 3 days, ERROR/CRITICAL 7 days (see app/notices.py)
    notice_interval: int = 0
    host: str = "0.0.0.0"
    port: int = 8631
    tls_certfile: str | None = None
    tls_keyfile: str | None = None
    # set only behind a TLS-terminating reverse proxy ("ipps"); default derives from the request
    public_scheme: str | None = None
    # Basic credentials over plain HTTP are refused unless this is set (tests / trusted lab only)
    allow_insecure_auth: bool = False
    timezone: str = "UTC"
    # language of the portal for visitors whose browser does not say (and for users who did not choose): en, it, es, ru, zh
    language: str = "en"
    default_group: str = "default"
    # Prepended to the user name CUPS sees. It can never equal a local account, so a RADIUS user
    # called "root" (or any member of CUPS' SystemGroup) cannot become a CUPS administrator.
    cups_user_prefix: str = "gw:"
    # answer Get-Printer-Attributes without login: required by IPP Everywhere clients to set a printer up
    anonymous_discovery: bool = True
    # eSCL scans without credentials (NAPS2 and others cannot send them): attributed to the guest account "ospite-scansione"
    escl_anonymous: bool = False
    max_request_mb: int = 200  # IPP request (document included) larger than this is refused
    reconcile_interval: float = 30.0  # seconds between CUPS job-state syncs
    secret_key: str | None = None  # signs admin session cookies; random per start if unset
    auto_create_users: bool = True

    # RADIUS is optional: leave host or secret empty and only local accounts exist
    radius_host: str = ""
    radius_port: int = 1812
    radius_secret: str = ""
    radius_timeout: int = 5
    auth_cache_seconds: int = 60

    # What a print client may present as password: "keys" = only personal print keys (default),
    # "keys+radius" = also the RADIUS password (transition; it encourages saving the domain password on clients)
    ipp_auth: str = "keys"
    key_ttl_days_radius: int = 90  # RADIUS-backed users must come back to the portal (a RADIUS login) to renew
    key_ttl_days_local: int = 365
    # public address of the portal, used in messages ("ask for more quota at ..."); derived from the request if empty
    portal_url: str = ""

    # first-run admin: created without a password, set with a one-time code printed in the log
    bootstrap_admin: bool = True
    bootstrap_admin_username: str = "cups_orchestrator"

    # printing from the browser (phones): largest accepted file and copies per job
    web_upload_mb: int = 25
    web_max_copies: int = 20

    max_open_requests: int = 3
    request_ttl_days: int = 14

    # audit: kept forever; when the active table outgrows this it is archived (compressed) to the folder below
    audit_max_mb: int = 50
    audit_archive_dir: str = "/data/audit-archive"
    audit_archive_host_path: str = ""  # shown in the portal only, so people know where the files are on the host
    audit_check_interval: float = 3600.0
    # warnings about the TLS certificate (the one in CUPSPL_TLS_CERTFILE). "Already expired" and "the announced address is
    # not in it" are always reported; "expires soon" only when asked for, so nobody gets a notice while the renewal is
    # simply not due yet.
    cert_expiry_warn_enabled: bool = False
    cert_expiry_warn_days: int = 14
    cert_name_check: bool = True
    # forget the names of printed files after some days (the rows, pages and states stay: quotas need them). Off by default.
    job_title_retention_enabled: bool = False
    job_title_retention_days: int = 90

    # eSCL scanner behind the gateway (ipp-usb serves it next to IPP); empty = scanning disabled
    scan_url: str = ""
    scan_timeout: float = 180.0  # a flatbed scan can take a while

    # What /healthz tells besides the status (it needs no login, so anyone who reaches the port can read it).
    # A comma-separated list; empty (default) = only the status. Known items: version, printers
    healthz_info: str = ""
    # Tell administrators when a newer release exists (one request a day to the URL below, nothing about this server is sent)
    update_check: bool = True
    # folder shared with the optional "updater" container (docker compose --profile autoupdate): requests go in, status comes out
    update_dir: str = "/data/update"
    update_api_url: str = "https://api.github.com/repos/deh-aleh/PrintMinder/releases/latest"

    # Printers page: how long what the printers say is reused, and every how many seconds the page reloads itself when the
    # administrator switches "automatic refresh" on. 0 (or anything unusable) = the default, 15.
    printers_refresh_seconds: int = 15

    # Finding printers by itself: USB printers are served either by the ipp-usb bridge (IPP over USB, preferred) or, for
    # printers that have no IPP-over-USB, by CUPS' own usb backend. A queue is created for each new device.
    auto_discover: bool = True
    discovery_interval: float = 30.0  # seconds between looks
    usb_bridge_host: str = "ipp-usb"  # empty = do not look for ipp-usb printers
    usb_bridge_ports: str = "60000-60099"  # the ports ipp-usb gives its printers (http-min-port..http-max-port)
    usb_direct: bool = True  # also look for USB printers that ipp-usb does not serve (CUPS usb backend, needs a driver)
    # a USB queue whose device stays unreachable this long is removed by itself (0 = never); network queues never are
    offline_remove_hours: float = 8.0

    # DNS-SD announcement (python -m app.mdns, container with host networking) so phones/computers find the printers
    mdns_hostname: str = ""  # name in the TLS certificate; default = host part of portal_url, else this machine's name
    mdns_addresses: str = ""  # comma separated IPv4 to advertise; default = the address of the default route
    mdns_port: int = 0  # 0 = the gateway port
    mdns_interval: float = 30.0  # seconds between looks at the CUPS queue list

    # backups: administrators pick a sub-folder of backup_root (the only place the gateway may write backups);
    # the "general" backup below is the one set in .env, the administrators' own are made in the portal
    backup_root: str = "/backups"
    backup_host_path: str = ""  # shown in the portal only: where backup_root is on the host
    backup_config_dir: str = "/config"  # read-only copy of config/ (TLS); saved only in encrypted backups
    backup_env_file: str = "/project.env"  # read-only copy of .env (settings, secrets); saved only in encrypted backups
    backup_enabled: bool = False
    backup_dir: str = "general"
    backup_hour: int = 3
    backup_require_marker: bool = False  # general backup: write only if the folder holds the marker file
    backup_keep_daily: int = 7
    backup_keep_weekly: int = 4
    backup_keep_monthly: int = 12
    backup_recipient: str = ""  # from `cups-policy-admin backup-key`; empty = no encryption (and no secrets in the file)


    @field_validator("printers_refresh_seconds", mode="after")
    @classmethod
    def _refresh_in_range(cls, v: int) -> int:
        return 15 if v <= 0 else min(max(v, 5), 3600)

    @property
    def radius_enabled(self) -> bool:
        return bool(self.radius_host and self.radius_secret)


settings = Settings()
