# The inference worker: models, container, configuration, operation

How AquaTrack is meant to run YOLO11m and RTMW-x on a newly uploaded video, and how far that
has got. Queue mechanics are in `docs/ANALYSIS_JOBS.md`; the test and its budget are in
`docs/GPU_ACCEPTANCE_TEST.md`; licences are in `docs/MODEL_LICENSING_DECISION.md`.

## 1. State (2026-11-16)

| | State |
| --- | --- |
| Worker process, queue, leases, cancel, clean-up | implemented; tested with fake inference adapters and the Firestore emulator |
| Model loading with integrity checks and a start-up preflight | implemented; tested with stand-in files and fake sessions |
| Container definition, model fetch and export scripts, job template | written; **never built or run** |
| **YOLO11m + RTMW-x actually running in the worker on a video** | **not done. No real inference has been run in Phase 8.** |

The models have run on these clips before, in Colab in Phase 1; those saved outputs are the
reference the first real worker run will be compared with. A test on saved pose data, or
with a fake adapter, is not an inference test.

## 2. Path of a video

    upload ─▶ Firebase Storage ─▶ Firestore job (queued)
                                        │ claim (lease)
                                        ▼
        worker: download ─▶ check the file ─▶ YOLO11m boxes ─▶ target swimmer (tracking)
                ─▶ RTMW-x 133 keypoints per frame ─▶ RawPose (schema 1.0, with model hashes)
                ─▶ cleanup and temporal processing ─▶ biomechanics ─▶ interpretation ─▶ feedback
                ─▶ Storage (pose arrays) + Firestore (analysis) ─▶ status ready ─▶ web app

Only the pose step differs from what runs today (`AQUATRACK_POSE_SOURCE=local` instead of
`precomputed`). Everything after RawPose is the code that already runs on the saved pose
data, and RawPose is validated against the video (hash, frame count, rate, size) whatever
produced it.

## 3. Models and their integrity

No weights are in the repository or in any personal account the worker depends on.

| File | Comes from | Check |
| --- | --- | --- |
| `yolo11m.pt` | Ultralytics' release asset (URL in `analysis/pose/manifest.py`) | size 40,684,120 bytes as the release reports; the release publishes no hash, so the SHA-256 is computed at build time and pinned |
| RTMW-x checkpoint (`.pth`) | OpenMMLab's download host | its SHA-256 must start with `f840f204`, as its file name states |
| `rtmw_x_stock.onnx` | exported from that checkpoint in a build stage (`scripts/export_rtmw_onnx.py`: mmpose 1.3.2 config, BN instead of SyncBN, outputs `simcc_x` / `simcc_y`, opset 17) | input `[1, 3, 384, 288]`, outputs `[1, 133, 576]` and `[1, 133, 768]`; SHA-256 pinned at build time |

ONNX exports are not bit-for-bit reproducible. The Phase 1 reference export has SHA-256
`5ff227bff950d1d1ace40631df82e2d6c8f6245b274446b5d66aaa05e7c67b29`; a new export will have a
different hash and may differ in the last decimals. That is why the build writes
`manifest.json` (name, bytes, SHA-256 of each file) next to the weights and the worker
checks the files against it at every start: the image is pinned to what was built and
tested, not to a hash from another export.

The official `onnx_sdk` RTMW-x model is a different generation with the same shapes and a
different score scale (`docs/POSE_PROCESSING.md`); the shape check cannot tell them apart,
the checksum and the acceptance comparison can.

### Preflight

Before it takes a job, a `local` worker (`python -m aquatrack.worker --check` runs just this):

1. reads the manifest (required in strict mode);
2. checks both files exist and match their size and SHA-256;
3. loads the detector and the pose model, never downloading anything;
4. checks the pose model's input and outputs;
5. if `AQUATRACK_POSE_DEVICE=cuda`, checks ONNX Runtime really uses `CUDAExecutionProvider`
   (it otherwise falls back to the CPU silently, about a hundred times slower);
6. runs one blank frame through both models.

Any failure: exit status 3, nothing claimed, no swimmer's attempt used. A job that meets a
bad model anyway fails once, not retryable, with "The analysis service is not set up
correctly. Nothing is wrong with your video."

Strict mode (`AQUATRACK_MODELS_STRICT=1`, and always in staging and production): a file not
in the manifest is refused. Outside it, for a developer's machine, an unlisted file loads
and is recorded as unverified.

## 4. Container

`worker/Dockerfile`, two stages, both on `python:3.11-slim`:

1. **export**: CPU PyTorch 2.5.1 and the MMPose tool chain of the Phase 1 export (mmengine
   0.10.7, mmcv-lite 2.1.0, mmpose 1.3.2, mmdet 3.3.0, `numpy<2`); downloads the checkpoint,
   checks it, exports the ONNX model, fetches the detector, writes the manifest.
2. **worker**: the locked application dependencies plus the `pose` extra (ultralytics
   8.4.210, the version that produced the reference pose; PyTorch 2.14.0, which brings the
   CUDA 13 and cuDNN 9 libraries as pip packages), `onnxruntime-gpu` 1.30 in place of
   `onnxruntime`, the `/models` folder from stage 1, an unprivileged user, and a build-time
   `--check` on CPU.

**One CUDA version throughout.** ONNX Runtime requires its CUDA and cuDNN to match the
libraries it loads, and documents its 1.27 to 1.30 GPU packages as built for CUDA 13.0 and
cuDNN 9; the unpinned newest package is also a CUDA 13 build. The locked PyTorch brings
CUDA 13. So there is no CUDA base image at all: both use the pip-installed libraries, and
the estimator calls `onnxruntime.preload_dlls()` before creating its session. An earlier
draft (Phase 8) used a CUDA 12 base image with an unpinned `onnxruntime-gpu`; that would
have paired a CUDA 13 build with CUDA 12 libraries and, at best, fallen back to the CPU. It
was found in Phase 9A by reading the lock file and ONNX Runtime's requirements, not by
running anything.

Both stages refuse to build without `ACCEPT_MODEL_TERMS=yes`, because building downloads the
weights (`docs/MODEL_LICENSING_DECISION.md`). The build runs in Cloud Build
(`worker/cloudbuild.yaml`, 45-minute limit), **never on the owner's Mac**, and its upload is
limited to an allowlist (`.gcloudignore`, `.dockerignore`): the application source and
scripts, nothing else. The image contains no credentials.

Not verified until a build and a GPU run: that the pinned export tool chain still installs;
that ONNX Runtime 1.30 and PyTorch 2.14 load the same CUDA 13 libraries under Cloud Run's
driver (580.x); the image size; frames per second and memory.

## 5. GPU environment

| Need | Value | Basis |
| --- | --- | --- |
| GPU | one NVIDIA L4 (24 GB) or T4 (16 GB) class card | assumed sufficient from model size; unmeasured |
| CPU / memory | 4 vCPU, 16 GiB (Cloud Run's minimum with an L4) | provider requirement |
| Disk | none persistent; working files in a temp folder, removed per job | on Cloud Run the filesystem is in memory, so a video counts against RAM |
| Network | outbound to Firestore and Cloud Storage only; no inbound endpoint | design |
| Identity | an attached service account with `roles/datastore.user` and object access to the one bucket | no key file |
| Speed, memory use, start-up time | **unknown** | measured by the acceptance test |

## 6. Configuration

| Variable | Meaning | Worker image default |
| --- | --- | --- |
| `AQUATRACK_ENV` | `emulator`, `test`, `staging`, `production` | set by the deployment |
| `AQUATRACK_POSE_SOURCE` | `local` for real inference | `local` |
| `AQUATRACK_POSE_DEVICE` | `cpu`, `cuda`, `mps` | `cuda` |
| `AQUATRACK_MODELS_DIR` | folder with the weights and `manifest.json` | `/models` |
| `AQUATRACK_MODELS_STRICT` | refuse files not in the manifest | `1` |
| `AQUATRACK_DETECTOR_WEIGHTS`, `AQUATRACK_POSE_WEIGHTS`, `AQUATRACK_DETECTOR_IMGSZ`, `AQUATRACK_DETECTOR_CONFIDENCE` | the model baseline; recorded with every result | `yolo11m.pt`, `rtmw_x_stock.onnx`, 640, 0.15 |
| `AQUATRACK_JOB_LEASE_S`, `AQUATRACK_JOB_TIMEOUT_S` | lease length; longest run | 120, 3600 |
| `AQUATRACK_PROGRESS_EVERY_S` | how often a running inference reports and looks for a stop | 5 |
| `AQUATRACK_WORKER_MAX_RSS_MB` | fail a job whose process outgrows this (0 = off) | 0 |
| `AQUATRACK_TMP_DIR` | where working files go | the system temp folder |
| `AQUATRACK_MAX_VIDEO_SECONDS` and the other file limits | checked on the file itself | 180 s |

Modes: `--check` (preflight only), `--once`, `--drain` (work until the queue is empty, then
exit: the mode for a job on a billed GPU), `--max-jobs N`, or a polling loop.

## 7. Privacy and safety of the worker

- It reads a video only by claiming that video's job; it never lists or serves videos, has
  no public endpoint and never creates a public or signed URL.
- Results are written under the video owner's own paths; the owner id comes from the stored
  video record, never from anything in the file.
- The downloaded video lives in a temp folder that is removed when the job ends, however it
  ends. Folders left by a killed worker are removed when the next worker starts.
- A result that was only partly written when a job failed or was cancelled is removed.
- Logs carry video ids, stage names and error classes: no file contents, no user-entered
  text, no tokens, no storage paths in user-facing errors.
- The image holds no credentials and no private data; weights are public files.
- While frames are being processed the worker looks every few seconds for a reason to stop
  (cancelled, video or account deleted, lease lost, time or memory limit) and then stores
  nothing.

Limits: the worker trusts the container for isolation; a crafted media file that crashes
the decoder kills the job (recovered twice, then failed). Least-privilege IAM is designed,
not yet applied to a real project.

## 8. Monitoring, recovery, shutdown

- **Health**: `GET /health/ready` on the API reports queued and running counts. The worker
  prints its preflight report as one JSON line at start.
- **Progress**: `job.progress` on the video (`stage`, and during inference `done` / `total`
  frames), shown to the swimmer on the video page.
- **Failures**: `job.errorCode` (stable), `job.errorMessage` (readable), `job.retryable`.
  Codes specific to real inference: `model_missing`, `model_checksum_mismatch`,
  `model_manifest_missing`, `model_not_in_manifest`, `model_incompatible`,
  `gpu_unavailable`, `pose_dependencies_missing`, `model_load_failed`, `worker_memory`,
  `timeout`, `worker_interrupted`.
- **Recovery**: none by hand. A dead worker's job is reclaimed when its lease runs out
  (2 minutes), at most twice.
- **Shutdown**: SIGTERM lets the current job reach its next checkpoint. In `--drain` mode
  the process exits by itself when the queue is empty, so a GPU never idles.
- To add at deployment: log-based alerts on preflight failures and on jobs older than a
  threshold, and a budget alert on the cloud project.

## 9. What is still open

1. The image has never been built; the models have never run in the worker. The exact
   steps to change that, once approved: `docs/PHASE_9B_EXECUTION.md`.
2. GPU speed, memory and cost per video are unmeasured.
3. Licences of both models (`docs/MODEL_LICENSING_DECISION.md`).
4. No Firebase project exists for the worker to connect to (stage 2 of the acceptance test).
5. The detector's SHA-256 is not pinned yet (first build).
