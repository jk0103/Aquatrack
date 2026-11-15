# Aquatrack

Personalized swim technique feedback from underwater or overhead video. Aquatrack tracks the
swimmer's body, measures things like stroke rate, left-right balance, rotation and kick rhythm,
and interprets them alongside the swimmer's goals, records and video history.

## Project layout

```
src/aquatrack/
  analysis/            # pure Python: video, pose, metrics (no web code)
    video.py           # read video info, iterate frames
    pose/              # pose backends (YOLO 17 points, RTMW-x 133 points) and cleanup
    metrics/           # stroke cycles and rate, technique measures, arm symmetry
    horizon.py         # travel direction (hip path or pool lines) for camera-tilt-free angles
    keyframes.py       # key-frame images with each measure drawn on
  api/                 # FastAPI app: accounts, video upload, analysis
tests/                 # pytest, uses synthetic videos and pose data
notebooks/             # experiments on sample videos
data/                  # sample and uploaded videos (gitignored)
frontend/              # Next.js web app, see frontend/README.md
firebase/              # Firestore and Storage security rules (firebase.json points here)
```

## Setup

Requires [uv](https://docs.astral.sh/uv/getting-started/installation/) (it installs Python 3.11 for you).

```bash
uv sync                  # core + dev tools
uv sync --extra pose     # also install pose estimation (Ultralytics YOLO, rtmlib + onnxruntime)
cp .env.example .env
```

## Everyday commands

```bash
uv run pytest                                   # tests
uv run ruff check . && uv run ruff format .     # lint + format
uv run uvicorn aquatrack.api.main:app --reload --env-file .env  # API on http://localhost:8000/docs
cd frontend && npm run dev                      # web app on http://localhost:3000
uv run python -m aquatrack.analysis.pose.cli VIDEO --overlay --device mps  # whole-body pose
```

Whole-body pose needs two weight files in `models/` (not in git): `rtmw_x_stock.onnx` (Google
Drive, `aquatrack_swim_full/rtmw/`) and `swim_pose.pt` (our swimmer detector; stock YOLO is
used if it's missing). Next to the video the CLI writes the raw points (`.wholebody.npz`), the
cleaned points with per-point confidence (`.clean.npz`), stroke cycles, stroke rate and swim
sections (`.cycles.json`), technique measures (`.measures.json`, with a key-frame image per
measure type in `VIDEO.measures/`), and with `--overlay` a skeleton video with a marker at
each cycle. `--distance-m` and `--time-s` add pace and distance per stroke.
`--device mps` runs RTMW on CoreML, about 4x faster than CPU with the same output; `--reuse`
re-runs cleanup and cycles from the saved raw points without the model.

## Local development with the Firebase emulators

No real Firebase project is used. Three processes (also in `.claude/launch.json`):

```bash
npm --prefix frontend run emulators      # Auth, Firestore, Storage (needs a JDK 21+ installed)
env FIREBASE_AUTH_EMULATOR_HOST=127.0.0.1:9099 FIRESTORE_EMULATOR_HOST=127.0.0.1:8080 \
    STORAGE_EMULATOR_HOST=http://127.0.0.1:9199 FIREBASE_PROJECT_ID=demo-aquatrack \
    uv run uvicorn aquatrack.api.main:app --reload --reload-dir src
env NEXT_PUBLIC_FIREBASE_EMULATORS=true npm --prefix frontend run dev
```

Upload → analysis: the web app uploads to Storage and calls `POST /videos/{id}/analyze`. The
API runs the job in the background and writes status and results to Firestore. Pose data
comes from a configurable source (`AQUATRACK_POSE_SOURCE`): `precomputed` (default; files
named `<video sha256>.rawpose.npz` in `data/precomputed_pose/`, produced in Colab), `local`
(needs the pose extra and weights) or `remote` (interface only). A video without pose data
fails with a clear reason; nothing is made up. See `docs/POSE_PROCESSING.md`.

## Roadmap

1. Run pose estimation on 5 to 10 sample clips (underwater side view and overhead) and see where tracking breaks.
2. Stroke rate and left-right symmetry working end to end on real clips.
3. Accounts, swimmer profiles and videos in Firebase (Auth, Firestore, Storage).
4. Personalized feedback text using the Claude API.
5. Web frontend with upload, results and progress history.
