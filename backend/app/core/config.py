from decimal import Decimal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "apartment103-backend"
    environment: str = "local"

    mongo_uri: str = "mongodb://localhost:27017"
    mongo_db: str = "apartment103"

    # Directory where uploaded image files are written. In production this
    # is a Docker volume shared read-only with nginx, which serves the files
    # directly (see deploy/nginx/templates/default.conf.template). Locally
    # it's a relative path under backend/, created on first upload.
    image_storage_path: str = "var/images"

    # Origins allowed to call the API from a browser (the Next.js frontend).
    cors_allow_origins: list[str] = ["http://localhost:3000"]

    # JWT access tokens issued after a successful OTP verification.
    jwt_secret_key: str = "insecure-dev-secret-change-me"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24

    # OTP codes.
    otp_length: int = 6
    otp_ttl_seconds: int = 300
    otp_resend_cooldown_seconds: int = 30
    otp_max_attempts: int = 5

    # SendGrid. Used to deliver OTP codes and booking/payment emails. When
    # sendgrid_api_key is unset (default), emails are logged instead of sent,
    # which is enough for local development.
    sendgrid_api_key: str | None = None
    sendgrid_from_address: str = "no-reply@apartment103.example"

    # Displayed on booking/payment emails and invoice PDFs.
    business_name: str = "Berg See Home"
    business_address: str | None = None

    # Stripe. stripe_secret_key/stripe_webhook_secret are backend-only
    # secrets; stripe_publishable_key is safe to hand to the frontend (it's
    # only used to construct Stripe.js on the client).
    stripe_secret_key: str | None = None
    stripe_webhook_secret: str | None = None
    stripe_publishable_key: str | None = None

    # Twilio. Used to deliver OTP codes by SMS. When twilio_account_sid or
    # twilio_auth_token is unset (default), SMS codes are logged instead of
    # sent, which is enough for local development.
    twilio_account_sid: str | None = None
    twilio_auth_token: str | None = None
    twilio_messaging_service_sid: str | None = None

    # Calendar sync (iCalendar/RFC 5545 — see docs/calendar-sync-design.md).
    # How often the inbound job re-polls every ExternalCalendar's feed.
    # Airbnb/Booking.com only regenerate their exports a few times a day, so
    # polling tighter than this buys nothing; polling much looser widens the
    # window in which a reservation taken there is still bookable here.
    calendar_sync_interval_minutes: int = 30
    calendar_sync_timeout_seconds: float = 30.0

    # Right-hand side of the UIDs in our outbound feed. Only has to be a
    # stable domain-shaped string; it is never resolved.
    calendar_uid_domain: str = "apartment103.example"

    # Optional site-wide export feed at /calendar/{token}.ics, carrying every
    # booking and closure. Each ExternalCalendar already has its own token
    # (ExternalCalendar.export_token); this one is for everything else — a
    # personal Google/Apple calendar, or verifying the feed format before
    # handing a URL to an OTA. Unset (the default) disables it. The URL is
    # the only credential an ICS consumer can present, so treat the value
    # like a secret.
    calendar_export_token: str | None = None

    # Markup applied on top of Stripe's FX rate when converting a CHF price
    # into a guest-facing non-CHF currency (see app/services/currency_service.py).
    commission_rate: Decimal = Decimal("0.06")

    # How long a Pending booking holds ("temporarily blocks") its nights
    # before it is swept away and the dates become bookable again — see
    # app.services.availability.expire_pending_bookings. A Pending booking is
    # created the moment a guest reaches checkout, so this is the window a
    # guest has to finish paying: long enough to fill in details and enter a
    # card, short enough that an abandoned checkout doesn't sit on the
    # calendar. The deadline is pushed back when the guest reaches the
    # payment step (see app.api.routes.payments.create_payment_intent).
    pending_booking_ttl_minutes: int = 15
    # How often the sweep job looks for expired Pending bookings. Expired
    # ones are also cleared on demand by the booking/availability paths, so
    # this is a bound on how stale the public calendar can get, not the only
    # thing standing between an abandoned checkout and the dates it holds.
    pending_booking_sweep_interval_minutes: int = 1


settings = Settings()
