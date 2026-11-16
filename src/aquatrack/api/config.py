"""Settings read from the environment (see .env.example), and the checks that keep one
environment from being mistaken for another.

AQUATRACK_ENV names where the process runs:

  emulator    local development against the Firebase Emulator Suite (the default)
  test        automated tests (in-memory store or the emulators)
  staging     a real, non-public Firebase project
  production  the live service

Nothing is deployed yet; staging and production exist here so that the day they are used,
a missing or left-over variable stops the process instead of pointing it at the wrong data.
"""

import os

# Firebase project the web app signs in with, e.g. "aquatrack-1234".
FIREBASE_PROJECT_ID = os.environ.get("FIREBASE_PROJECT_ID") or None

# Path to the service account key JSON. Keep the file outside the repo; never commit it.
FIREBASE_CREDENTIALS = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS") or None

ENVIRONMENTS = ("emulator", "test", "staging", "production")
EMULATOR_HOSTS = ("FIREBASE_AUTH_EMULATOR_HOST", "FIRESTORE_EMULATOR_HOST", "STORAGE_EMULATOR_HOST")


def environment() -> str:
    return os.environ.get("AQUATRACK_ENV", "emulator").strip().lower()


def worker_mode() -> str:
    """embedded: a worker thread inside the API (development). external: the API only
    queues, and `python -m aquatrack.worker` processes do the work."""
    return os.environ.get("AQUATRACK_WORKER", "embedded").strip().lower()


def is_real_project() -> bool:
    return environment() in ("staging", "production")


def validate(role: str = "api") -> list[str]:
    """Everything wrong with the configuration, in plain words. Empty means usable. Values
    of secrets are never included in a message."""
    env = os.environ
    problems: list[str] = []
    name = environment()
    if name not in ENVIRONMENTS:
        return [f"AQUATRACK_ENV must be one of {', '.join(ENVIRONMENTS)}."]
    project = env.get("FIREBASE_PROJECT_ID", "")
    emulators = [h for h in EMULATOR_HOSTS if env.get(h)]
    if name in ("emulator", "test"):
        if env.get("GOOGLE_APPLICATION_CREDENTIALS"):
            problems.append(
                "GOOGLE_APPLICATION_CREDENTIALS is set in a local environment. Unset it: "
                "local runs must never hold credentials for a real project."
            )
        if env.get("AQUATRACK_ALLOW_PRODUCTION_FIREBASE") == "1":
            problems.append("AQUATRACK_ALLOW_PRODUCTION_FIREBASE=1 is not allowed locally.")
        if project and not project.startswith("demo-"):
            problems.append(
                "FIREBASE_PROJECT_ID must start with 'demo-' locally, so the emulators can "
                "never forward to a real project."
            )
        if name == "emulator" and len(emulators) != len(EMULATOR_HOSTS):
            missing = [h for h in EMULATOR_HOSTS if h not in emulators]
            problems.append("Emulator hosts are not all set: " + ", ".join(missing) + ".")
    else:
        if emulators:
            problems.append(
                f"{', '.join(emulators)} set in {name}: a real environment must not use emulators."
            )
        if not project or project.startswith("demo-"):
            problems.append(f"FIREBASE_PROJECT_ID must name the real {name} project.")
        if env.get("AQUATRACK_ALLOW_PRODUCTION_FIREBASE") != "1":
            problems.append(
                "AQUATRACK_ALLOW_PRODUCTION_FIREBASE=1 is required to use a real project."
            )
        if env.get("AQUATRACK_POSE_SOURCE", "precomputed").lower() == "precomputed" and (
            role == "worker" or worker_mode() == "embedded"
        ):
            problems.append(
                "AQUATRACK_POSE_SOURCE=precomputed is a development fixture and cannot "
                f"analyse new uploads; {name} needs a worker with AQUATRACK_POSE_SOURCE=local."
            )
        if name == "production" and role == "api" and worker_mode() != "external":
            problems.append(
                "Production runs the worker as its own process: AQUATRACK_WORKER=external."
            )
    if worker_mode() not in ("embedded", "external"):
        problems.append("AQUATRACK_WORKER must be 'embedded' or 'external'.")
    provider = env.get("AQUATRACK_LLM_PROVIDER", "").strip().lower()
    if provider not in ("", "none", "off", "openai"):
        problems.append("AQUATRACK_LLM_PROVIDER must be empty or 'openai'.")
    if provider == "openai" and not env.get("OPENAI_API_KEY"):
        problems.append("AQUATRACK_LLM_PROVIDER=openai needs OPENAI_API_KEY (rewording stays off).")
    return problems
