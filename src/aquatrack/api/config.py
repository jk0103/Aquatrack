"""Settings read from the environment (see .env.example)."""

import os

# Firebase project the web app signs in with, e.g. "aquatrack-1234".
FIREBASE_PROJECT_ID = os.environ.get("FIREBASE_PROJECT_ID") or None

# Path to the service account key JSON. Keep the file outside the repo; never commit it.
FIREBASE_CREDENTIALS = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS") or None
