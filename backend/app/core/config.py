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


settings = Settings()
