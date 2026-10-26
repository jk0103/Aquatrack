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
    metrics/           # stroke cycles and rate, arm symmetry, ... (more to come)
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
sections (`.cycles.json`), and with `--overlay` a skeleton video with a marker at each cycle.
`--device mps` runs RTMW on CoreML, about 4x faster than CPU with the same output; `--reuse`
re-runs cleanup and cycles from the saved raw points without the model.

## Roadmap

1. Run pose estimation on 5 to 10 sample clips (underwater side view and overhead) and see where tracking breaks.
2. Stroke rate and left-right symmetry working end to end on real clips.
3. Accounts, swimmer profiles and videos in Firebase (Auth, Firestore, Storage).
4. Personalized feedback text using the Claude API.
5. Web frontend with upload, results and progress history.
