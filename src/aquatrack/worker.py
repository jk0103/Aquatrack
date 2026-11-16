"""The analysis worker as its own process.

    uv run python -m aquatrack.worker            # run until stopped
    uv run python -m aquatrack.worker --drain    # work until the queue is empty, then exit
    uv run python -m aquatrack.worker --once     # handle at most one job, then exit
    uv run python -m aquatrack.worker --check    # check configuration and models, then exit

It takes jobs from the same durable queue the API writes to (see aquatrack.api.jobs), so it
can run on a different machine from the API: all it needs is access to Firestore and
Storage, and a pose source. Which pose source it uses comes from AQUATRACK_POSE_SOURCE:

  precomputed  pose files made elsewhere (development fixture; not real inference)
  local        YOLO11m + RTMW-x in this process (needs the `pose` extra and the model files
               with their manifest in AQUATRACK_MODELS_DIR; AQUATRACK_POSE_DEVICE=cuda for
               a GPU). This is what a real inference worker runs.

Before it takes any job a `local` worker checks its model files against the manifest, the
pose model's inputs and outputs, and that a requested GPU is really in use. If any of that
fails it exits with status 3 and takes nothing, so a broken image cannot use up anyone's
attempts. Exit codes: 0 fine, 2 configuration, 3 models.

Stopping it (Ctrl-C or SIGTERM) lets the current job reach its next checkpoint; a job cut
off part way is recovered by the queue when its lease runs out. Start as many workers as you
like: a job is only ever claimed by one of them. Working files are removed after every job,
and leftovers from a killed worker are removed at start.
"""

import argparse
import json
import logging
import signal
import sys

from aquatrack.analysis.pose.sources import pose_source_from_env
from aquatrack.api import config, jobs
from aquatrack.api.jobs import Worker
from aquatrack.contracts import ModelConfig

log = logging.getLogger("aquatrack.worker")


def preflight(source) -> dict | None:
    """The model check of a source that has one (None for sources without models)."""
    check = getattr(source, "preflight", None)
    return check().to_dict() if check else None


def main(argv: list[str] | None = None, store_factory=None) -> int:
    parser = argparse.ArgumentParser(description="AquaTrack analysis worker")
    parser.add_argument("--once", action="store_true", help="handle at most one job and exit")
    parser.add_argument("--drain", action="store_true", help="exit when the queue is empty")
    parser.add_argument("--max-jobs", type=int, default=None, help="exit after this many jobs")
    parser.add_argument("--check", action="store_true", help="check config and models, then exit")
    parser.add_argument("--poll", type=float, default=5.0, help="seconds between queue checks")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")

    problems = config.validate(role="worker")
    if problems:
        for line in problems:
            print(f"configuration error: {line}", file=sys.stderr)
        return 2
    try:
        source = pose_source_from_env(ModelConfig.from_env())
    except ValueError as e:
        print(f"configuration error: {e}", file=sys.stderr)
        return 2

    report = preflight(source)
    if report is not None:
        print(json.dumps({"preflight": report}, sort_keys=True))
        if not report["ok"]:
            print(f"model check failed: {report['error_code']}: {report['error']}", file=sys.stderr)
            return 3
    if args.check:
        print("configuration and models are usable" if report else "configuration is usable")
        return 0

    removed = jobs.clean_work_dirs(older_than_s=jobs.JOB_TIMEOUT_S)
    if removed:
        log.info("removed %s working folder(s) left by an earlier worker", removed)
    if store_factory is None:
        from aquatrack.api.store import FirebaseStore

        store_factory = FirebaseStore
    worker = Worker(store_factory(), source)
    if args.once:
        print("handled one job" if worker.run_once() else "no job waiting")
        return 0
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: worker.stop())
    worker.run_forever(args.poll, drain=args.drain, max_jobs=args.max_jobs)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
