from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    MONGO_URL: str = "mongodb://localhost:27017"
    DB_NAME: str = "repsandgreens"   # kept: the live database already uses this name
    JWT_SECRET: str = "dev-secret-change-me"
    JWT_EXPIRES_MIN: int = 10080          # access token lifetime (legacy default; lower in prod + use refresh)
    REFRESH_EXPIRES_DAYS: int = 30        # refresh token lifetime
    RESET_TOKEN_EXPIRES_MIN: int = 30     # password-reset link lifetime

    # public base URL used to build links in emails (reset password, etc.)
    BASE_URL: str = "http://localhost:8000"

    # commerce
    MEMBER_DISCOUNT_PCT: float = 0.15     # loyalty discount applied to every cart
    TAX_PCT: float = 0.0                  # e.g. 0.18 for 18% GST; 0 disables tax

    # caching / real-time (optional — falls back to in-process when unset)
    REDIS_URL: str = ""

    # push notifications (Firebase Cloud Messaging HTTP v1 or legacy server key)
    FCM_SERVER_KEY: str = ""

    # Apple Sign-In
    APPLE_CLIENT_ID: str = ""             # your app's services/bundle id (aud)

    # cloud storage — STORAGE_BACKEND = local | s3 | cloudinary
    STORAGE_BACKEND: str = "local"
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    AWS_S3_BUCKET: str = ""
    AWS_S3_REGION: str = "ap-south-1"
    CLOUDINARY_URL: str = ""

    COACH_EMAIL: str = "coach@merova.app"
    COACH_NAME: str = "Merova Coach"          # shown to clients in the app
    COACH_PASSWORD: str = "change-me"
    RAZORPAY_KEY_ID: str = ""
    RAZORPAY_KEY_SECRET: str = ""
    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_AUTH_TOKEN: str = ""
    TWILIO_WA_FROM: str = "whatsapp:+14155238886"
    RESEND_API_KEY: str = ""
    EMAIL_FROM: str = "Merova Fit <hello@merova.app>"
    GOOGLE_CLIENT_ID: str = ""
    FRONTEND_ORIGIN: str = "http://localhost:5173"
    ENV: str = "development"              # development | production
    LOG_LEVEL: str = "INFO"
    MAX_UPLOAD_MB: int = 8
    RAZORPAY_WEBHOOK_SECRET: str = ""
    # Android app (Trusted Web Activity) — from PWABuilder / Bubblewrap signing details
    ANDROID_PACKAGE: str = ""
    ANDROID_CERT_SHA256: str = ""

settings = Settings()
