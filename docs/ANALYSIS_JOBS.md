# Analysis jobs, the worker, and production inference

Code: `src/aquatrack/api/jobs.py` (queue, leases, worker loop), `src/aquatrack/worker.py`
(the worker as its own process), `src/aquatrack/analysis/pose/sources.py` (pose sources).

## 1. What a new upload needs, and what exists

| Step | Exists | How it was checked |
| --- | --- | --- |
| 1. Upload a video | yes | browser journey, security rules |
| 2. A job is queued durably | yes | unit, emulator and browser tests |
| 3. A worker claims it and fetches the video | yes | fake adapters, emulator |
| 4. The file itself is validated (size, length, resolution, readable) | yes | unit tests |
| 5. **Pose estimation on that video** | **only for videos whose pose file already exists** | saved model output for 3 public clips |
| 6. Biomechanics, interpretation, feedback | yes | real pose data and synthetic data |
| 7. Results stored, history and training updated | yes | all levels |

Step 5 is the gap. `AQUATRACK_POSE_SOURCE=precomputed` looks a pose file up by the video's
hash; it cannot analyse a video nobody processed beforehand. `local` runs YOLO11m and RTMW-x
inside the worker and is what a production worker would use, but it has **not been run in
this worker on a new video**: the weights are not on this machine (by instruction) and no
GPU host is approved. Until one real upload goes through `local` on a real worker and its
numbers are compared with the saved results, arbitrary-video inference is not validated.
Phase 8 prepared that run (model checks, container, acceptance test, budget) without
executing it: `docs/INFERENCE_WORKER.md`, `docs/GPU_ACCEPTANCE_TEST.md`.

## 2. Target architecture

    browser ──upload──▶ Firebase Storage
       │
       └─▶ FastAPI (Render) ──"queued"──▶ Firestore videos/{id}   ◀── the queue
                                             ▲        │
                                 lease, progress,     │ claim (transaction)
                                 result               ▼
                                          inference worker (GPU, scale to zero)
                                          python -m aquatrack.worker
                                          reads the video from Storage, writes
                                          pose artifacts and the analysis

- The API never runs inference and never receives the file.
- The worker needs: read access to `videos/`, write access to `analysis/`, Firestore access,
  the two weight files baked into its image or on a mounted volume. It never talks to the
  browser and has no public endpoint.
- Weights come from the public sources at build time: `yolo11m.pt` from Ultralytics'
  release, and the RTMW-x checkpoint from OpenMMLab exported to ONNX with the documented
  export (see `docs/POSE_PROCESSING.md`). **Not** from a student's Google Drive, and **not**
  from Colab.
- A scale-to-zero worker is started per job (`--once`) by the platform's job trigger, or runs
  a polling loop while there is work. Hosting options: `docs/DEPLOYMENT_PLAN.md`.

## 3. The queue

The queue is the video documents. Firestore-backed leasing was chosen over a dedicated queue
(Cloud Tasks, Pub/Sub, Redis) because it adds no service, no cost and no second source of
truth, and one transaction per claim is plenty at the expected volume (a handful of jobs an
hour). Its limits: it polls (default every 5 s), `list_pending_videos` reads every pending
job each time, and there is no priority or fairness beyond oldest-first plus a per-swimmer
cap. Past roughly a few hundred jobs an hour, or if workers must be woken instantly, a
dedicated queue becomes the better choice.

| Property | How |
| --- | --- |
| Durable queued state | `status: queued` and the `job` map are written in the request's transaction |
| Atomic claim | `claim()` is one transaction: queued → analyzing with `leaseOwner`, `leaseExpiresAt` |
| Lease and heartbeat | the worker renews at each stage and on a timer (`LEASE_S / 3`) during long steps |
| Recovery | an expired lease makes the job claimable again; `interruptions` counts recoveries |
| No endless loops | after `MAX_INTERRUPTIONS` (2) recoveries the job fails with `worker_interrupted` |
| Retry limits | `MAX_ATTEMPTS` failures per video, as before |
| No duplicate processing | only the lease holder may finish a job (`_finish` checks the owner in a transaction) |
| Idempotent results | `analysisId` is fixed when the job is queued; a rerun writes the same documents |
| Cancellation | `POST /videos/{id}/cancel`: queued → cancelled at once; running → flagged, the worker stops at its next checkpoint and stores nothing; a cancelled run costs no attempt |
| Timeout | `JOB_TIMEOUT_S` (default 1 h) checked at every heartbeat |
| Ownership | request and cancel check the caller; a worker only ever acts on the queue |
| Deletion | `deleting` ends the lease check: the worker stops, and anything written in the gap is removed |
| Flood protection | `MAX_ACTIVE_JOBS` (2) queued or running per swimmer, plus request rate limits |
| Progress | `job.progress.stage`: starting, downloading, checking, pose, measuring, saving |
| Failure reporting | `job.errorCode`, `job.errorMessage` (readable, no paths), `job.retryable` |

During the pose step a source that reports per frame (the real `local` source does) is
stopped within a few seconds of a cancellation, a deletion, a lost lease, or the time or
memory limit (Phase 8); it also reports `done` / `total` frames as progress. The
`precomputed` fixture has no frames to report and is checked between stages. A result that
was only partly written when a job fails or is cancelled is removed, and working folders
left by a killed worker are removed when the next one starts.

## 4. Running it

Development (default): the API runs an embedded worker thread (`AQUATRACK_WORKER=embedded`).
It reads the same queue, so jobs left from before a restart are picked up when the API starts.

Separate worker:

    AQUATRACK_WORKER=external uv run uvicorn aquatrack.api.main:app      # API: queues only
    uv run python -m aquatrack.worker                                     # worker: loop
    uv run python -m aquatrack.worker --once                              # one job, then exit

The worker refuses to start if its configuration is unsafe (`config.validate("worker")`), for
example a real project with the precomputed fixture.

Recovery: a stuck job needs no manual step; it is reclaimed when its lease expires (2 minutes
by default) or the swimmer cancels it. `GET /health/ready` shows how many jobs are queued and
running.

## 5. Tests

`tests/test_queue.py` (in memory, fake inference adapters): restart recovery, 8 workers
claiming at once, oldest first, lease expiry, the interruption limit, a stalled worker that
wakes up after another finished, idempotent reruns, heartbeats, timeout, failure while
saving, cancel in every state, deletion mid-run, the per-swimmer cap, file limits, a
non-video file, a flaky queue. `tests/test_emulator_backend.py`: the same claims and
conflicts through real Firestore transactions in the emulator. One regression test runs a
real public clip through the worker with saved model output (skipped where those local files
are absent).

Not tested: two workers on different machines, real model inference, memory use, GPU
failures, Firestore quota or contention at volume.
