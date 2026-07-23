from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    app_name: str = "apartment103-backend"
    environment: str = "local"

    mongo_uri: str = "mongodb://localhost:27017"
    mongo_db: str = "apartment103"

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

    # SMTP settings used to deliver OTP codes by email. When smtp_host is
    # unset (default), emails are logged instead of sent, which is enough
    # for local development.
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_use_tls: bool = True
    smtp_from_address: str = "no-reply@apartment103.example"

    # Stripe. stripe_secret_key/stripe_webhook_secret are backend-only
    # secrets; stripe_publishable_key is safe to hand to the frontend (it's
    # only used to construct Stripe.js on the client).
    stripe_secret_key: str | None = None
    stripe_webhook_secret: str | None = None
    stripe_publishable_key: str | None = None


settings = Settings()
