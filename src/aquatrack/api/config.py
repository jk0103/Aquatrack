"""Settings read from the environment (see .env.example)."""

import os

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///data/aquatrack.db")

# Signs login session cookies. The default is only for local development.
SECRET_KEY = os.environ.get("AQUATRACK_SECRET_KEY", "dev-only-insecure-secret-change-me")

SESSION_DAYS = int(os.environ.get("AQUATRACK_SESSION_DAYS", "7"))

# Set to true when served over HTTPS so the session cookie is never sent in plain text.
COOKIE_SECURE = os.environ.get("AQUATRACK_COOKIE_SECURE", "false").lower() == "true"
