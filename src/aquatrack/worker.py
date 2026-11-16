"""The analysis worker as its own process.

    uv run python -m aquatrack.worker            # run until stopped
    uv run python -m aquatrack.worker --once     # handle at most one job, then exit

It takes jobs from the same durable queue the API writes to (see aquatrack.api.jobs), so it
can run on a different machine from the API: all it needs is access to Firestore and
Storage, and a pose source. Which pose source it uses comes from AQUATRACK_POSE_SOURCE:

  precomputed  pose files made elsewhere (development fixture; not real inference)
  local        YOLO + RTMW on this machine (needs the `pose` extra and the weights in
               AQUATRACK_MODELS_DIR; this is what a production inference worker runs)

Stopping it (Ctrl-C or SIGTERM) lets the current job finish its step; a job cut off part way
is recovered by the queue when its lease runs out. Start as many workers as you like: a job
is only ever claimed by one of them.
"""

import argparse
import logging
import signal
import sys

from aquatrack.analysis.pose.sources import pose_source_from_env
from aquatrack.api import config
from aquatrack.api.jobs import Worker
from aquatrack.api.store import FirebaseStore
from aquatrack.contracts import ModelConfig


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AquaTrack analysis worker")
    parser.add_argument("--once", action="store_true", help="handle at most one job and exit")
    parser.add_argument("--poll", type=float, default=5.0, help="seconds between queue checks")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    problems = config.validate(role="worker")
    if problems:
        for line in problems:
            print(f"configuration error: {line}", file=sys.stderr)
        return 2
    worker = Worker(FirebaseStore(), pose_source_from_env(ModelConfig.from_env()))
    if args.once:
        print("handled one job" if worker.run_once() else "no job waiting")
        return 0
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: worker.stop())
    worker.run_forever(args.poll)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
