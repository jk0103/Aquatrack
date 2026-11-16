"""Settings read from the environment (see .env.example), and the checks that keep one
environment from being mistaken for another.

AQUATRACK_ENV names where the process runs:

  emulator    local development against the Firebase Emulator Suite (the default)
  test        automated tests (in-memory store or the emulators)
  staging     a real, non-public Firebase project
  production  the live service

Staging may also be the restricted school demonstration (AQUATRACK_DEMO=1 with
AQUATRACK_ACCESS=restricted): see the section on restricted access below.

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


# --- Restricted access and the school demonstration -------------------------------------
#
# AQUATRACK_ACCESS=restricted: only the accounts whose Firebase uid is listed in
# AQUATRACK_ALLOWED_UIDS may use the API. The same accounts carry the custom claim
# ACCESS_CLAIM, which the restricted security rules (firebase/restricted/) require, so an
# account that is not listed can neither call the backend nor read or write Firestore and
# Storage directly, whether or not it managed to sign up.
#
# AQUATRACK_DEMO=1: the demonstration environment. Analysis reuses pose data extracted
# earlier from the approved test video (the `precomputed` source); the pose models do not
# run. It is accepted only in staging (or locally), only together with restricted access,
# and never in production: see validate() and fixture_problem().

ACCESS_CLAIM = "aquatrack_demo"
ACCESS_DENIED = "This account is not authorized to use this AquaTrack demonstration."


def access_mode() -> str:
    return os.environ.get("AQUATRACK_ACCESS", "open").strip().lower() or "open"


def restricted() -> bool:
    # Anything other than an explicit "open" is treated as restricted: a typo closes the
    # door instead of opening it.
    return access_mode() != "open"


def allowed_uids() -> frozenset[str]:
    raw = os.environ.get("AQUATRACK_ALLOWED_UIDS", "")
    return frozenset(part.strip() for part in raw.replace("\n", ",").split(",") if part.strip())


def is_allowed(uid: str) -> bool:
    return not restricted() or uid in allowed_uids()


def demo_mode() -> bool:
    return os.environ.get("AQUATRACK_DEMO", "").strip() == "1"


def pose_source_name() -> str:
    return os.environ.get("AQUATRACK_POSE_SOURCE", "precomputed").strip().lower()


def fixture_problem() -> str | None:
    """Why saved pose data may not be used for analysis here, or None when it may. Local
    environments may always use it (development fixture). A real project may only as the
    restricted demonstration, and production never."""
    if pose_source_name() != "precomputed" or not is_real_project():
        return None
    if environment() == "production":
        return (
            "AQUATRACK_POSE_SOURCE=precomputed is a development fixture and is never used "
            "in production."
        )
    if not demo_mode():
        return (
            "AQUATRACK_POSE_SOURCE=precomputed is a development fixture and cannot analyse "
            "new uploads; staging uses it only as the restricted demonstration (AQUATRACK_DEMO=1)."
        )
    if access_mode() != "restricted":
        return "The demonstration (AQUATRACK_DEMO=1) requires AQUATRACK_ACCESS=restricted."
    return None


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
        problem = fixture_problem()
        if problem and (role == "worker" or worker_mode() == "embedded"):
            problems.append(problem)
        if name == "production" and role == "api" and worker_mode() != "external":
            problems.append(
                "Production runs the worker as its own process: AQUATRACK_WORKER=external."
            )
    if access_mode() not in ("open", "restricted"):
        problems.append("AQUATRACK_ACCESS must be 'open' or 'restricted'.")
    if demo_mode():
        if name == "production":
            problems.append("AQUATRACK_DEMO=1 is never allowed in production.")
        if access_mode() != "restricted":
            problems.append("AQUATRACK_DEMO=1 requires AQUATRACK_ACCESS=restricted.")
        if pose_source_name() != "precomputed":
            problems.append(
                "AQUATRACK_DEMO=1 uses saved pose data: AQUATRACK_POSE_SOURCE=precomputed."
            )
    if access_mode() == "restricted" and is_real_project() and not allowed_uids():
        problems.append(
            "AQUATRACK_ACCESS=restricted with no AQUATRACK_ALLOWED_UIDS: nobody can sign in."
        )
    if worker_mode() not in ("embedded", "external"):
        problems.append("AQUATRACK_WORKER must be 'embedded' or 'external'.")
    provider = env.get("AQUATRACK_LLM_PROVIDER", "").strip().lower()
    if provider not in ("", "none", "off", "openai"):
        problems.append("AQUATRACK_LLM_PROVIDER must be empty or 'openai'.")
    if provider == "openai" and not env.get("OPENAI_API_KEY"):
        problems.append("AQUATRACK_LLM_PROVIDER=openai needs OPENAI_API_KEY (rewording stays off).")
    return problems
