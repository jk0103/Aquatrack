# Phase 9B execution package: the first real GPU inference test

**Status: prepared, not approved, not run.** No cloud project, billing link, image, job or
bucket exists. Nothing here starts by itself.

## Decision gate

Phase 9B needs the owner's separate, explicit approval of **each** of these:

1. the permitted use of the two models for this test (section 1);
2. the provider and GPU (section 2);
3. the billing exposure (section 3);
4. the resources to be created (section 4);
5. running the real inference (section 6).

Being technically ready is not approval. Until all five are given, the commands below are
documentation.

## 1. Rights and permissions

Full detail: `docs/MODEL_LICENSING_DECISION.md`.

| Question | State |
| --- | --- |
| May the unmodified `ultralytics` package and `yolo11m.pt` be run once, privately, on public video, for no users? | **Disputed.** The AGPL-3.0 text permits running the unmodified program privately and nothing is conveyed. Ultralytics' published policy says closed R&D and evaluation need a paid licence (it sells an "R&D License" for exactly that) and offers free evaluation only "in a fully open-source environment". **No permission from the licensor exists.** |
| May the RTMW-x cocktail14 checkpoint be converted to ONNX and run once, privately, for research? | No terms are published for the checkpoint. Every dataset restriction found permits research and non-commercial use. **Not confirmed by the publisher.** |
| Is a commercial or paid use cleared? | **No.** Out of scope for this test. |
| Is the test video usable? | "Front Crawl Underwater", Wikimedia Commons, CC BY-SA 4.0: use and adaptation allowed with attribution; nothing derived from it is redistributed. |

**Is there sufficient documented authorisation for a controlled private research test? No,
not from the rights holders.** What exists is: the AGPL-3.0 text and the FSF's reading of
it, which permit private use, and dataset terms that permit research. What is missing is
anything from Ultralytics (whose own pages point the other way while the project is closed)
and any terms at all for the RTMW-x checkpoint. The owner chooses one of four ways before
approving the test (`docs/MODEL_LICENSING_DECISION.md`, section 6): ask first; publish under
AGPL-3.0 first; buy Ultralytics' R&D licence; or proceed on the licence text alone as a
known risk. The test changes nothing about what a public or commercial use needs.

## 2. Provider and GPU

Google Cloud Run **job**, one NVIDIA L4, 4 vCPU, 16 GiB, region `us-central1`, no zonal
redundancy. Reasons and the Modal comparison: `docs/GPU_ACCEPTANCE_TEST.md`. No blocker to
Cloud Run was found in the documentation. Fallback if the automatic L4 quota is not granted:
stop and report; do not improvise.

## 3. Cost and exposure

Prices are Google's published us-central1 rates read on 2026-11-16. "Derived" is arithmetic
on them; "assumed" is unmeasured.

| Item | Bound that is enforced by the platform | Cost |
| --- | --- | --- |
| One job execution | 1 task, 0 retries, task timeout 15 minutes (Cloud Run kills it) | at most $0.26 (derived: 900 s x $0.0002907); the first minute is always billed |
| All executions | 5 at most: a counter in `worker/phase9b.sh`, **not** a platform limit | at most $1.31 (derived) |
| Expected executions | 1 to 3, a few minutes each (assumed) | $0.05 to $0.30 (assumed) |
| Image build | Cloud Build timeout 45 minutes, default machine at $0.006/min; 2,500 free minutes a month per billing account | $0 inside the free minutes, at most $0.27 otherwise (derived); a rebuild doubles it |
| Image storage | none | about $0.10 per GiB-month after 0.5 GiB free: about $0.03 a day for 8 GiB (derived) |
| Result bucket, build source bucket | none | under $0.01; deleted objects are kept (and billed) 7 days by soft delete |
| Logs | 50 GiB a month free | $0 (usage is kilobytes) |
| Network | download into Cloud Run is free; same-region transfer is free | $0 |
| **Expected total** | | **under $1** (assumed) |
| **Conservative ceiling** | | **$5**: every execution at its limit, two full builds off the free tier, a week of forgotten storage |

### What cannot be guaranteed

- **A budget alert does not stop spending.** Google's budget page says an alerts-only budget
  "doesn't automatically cap" usage, and that cost data and alerts arrive hours late.
- **A spend cap exists but is not a hard guarantee.** Since October 2026 "spend cap budgets"
  are generally available for a few services including Cloud Run: at the cap, new job
  executions fail to start and running ones fail. Google states enforcement "isn't instant"
  and overage is billed. It covers one project and one service, so **Cloud Build, Artifact
  Registry, Cloud Storage and Logging are outside it.**
- The 5-execution limit is our own script's counter. Someone running `gcloud` by hand is
  not bound by it.
- The L4 quota given to a new project is 3, not 1; parallelism is set to 1 by us.
- Charges already incurred can appear on the bill a day or more after shutdown.

So: actual charges **cannot be promised** to stay under any figure. What bounds them in
practice is the per-execution timeout with no retries, a single task, the small number of
steps, a dedicated project that is deleted, and billing being unlinked at the end.
Recommended on top: a Cloud Run spend cap budget of $5 on the test project and an
alerts-only budget of $5 for the whole project.

## 4. What must exist (created by the owner; none exists)

| Resource | Created by | Removed by |
| --- | --- | --- |
| A Google account with a billing account | owner (card required) | stays |
| A new, dedicated project, e.g. `aquatrack-9b-test` | owner | `gcloud projects delete` |
| Billing link on that project | owner | `gcloud billing projects unlink` |
| Budgets: $5 alerts-only for the project; $5 spend cap for Cloud Run | owner, in the console | deleted with the project |
| APIs: Cloud Run, Artifact Registry, Cloud Build, Cloud Storage | `phase9b.sh setup` | project deletion |
| Artifact Registry repository `aquatrack-test` (us-central1) | `phase9b.sh setup` | `phase9b.sh cleanup` |
| Bucket `gs://PROJECT_ID-acceptance-out` (us-central1) | `phase9b.sh setup` | `phase9b.sh cleanup` |
| Bucket `gs://PROJECT_ID_cloudbuild` (made by Cloud Build) | automatically | `phase9b.sh cleanup` |
| Cloud Run job `aquatrack-acceptance` | `phase9b.sh create` | `phase9b.sh stop` or `cleanup` |

No Firebase project, no service-account key, no secret, no personal data. The job runs as
the project's default identity and needs write access to the one result bucket only. The
build uploads only what `.gcloudignore` allows: `pyproject.toml`, `uv.lock`, `README.md`,
`src/`, `scripts/`, `worker/`.

## 5. Owner set-up (not done)

1. Create the project in the Google Cloud console and link a billing account.
2. Billing, Budgets and alerts: create the two budgets above.
3. Open **Cloud Shell** in that project (the Mac has no `gcloud` or `docker`, and must not
   download the weights).
4. Get the code into Cloud Shell without publishing it: upload an archive made on the Mac
   with `git archive --format=zip -o aquatrack.zip HEAD` (tracked files only: no videos, pose
   data, experiments or documents that are ignored). Nothing is pushed to GitHub.

## 6. Commands (in Cloud Shell; not run)

    export PROJECT_ID=aquatrack-9b-test
    export ACCEPT_MODEL_TERMS=yes          # the owner's acceptance for this test
    bash worker/phase9b.sh check           # read-only: project, billing, existing jobs
    bash worker/phase9b.sh setup           # APIs, image repository, result bucket
    bash worker/phase9b.sh build           # one Cloud Build (up to 45 min)
    bash worker/phase9b.sh create          # the job: 1 L4, 1 task, 0 retries, 15 min
    bash worker/phase9b.sh run             # one execution, waits for it
    bash worker/phase9b.sh status
    bash worker/phase9b.sh fetch           # acceptance.json and the new RawPose

Then, on the Mac, with the fetched pose file (no models needed):

    uv run python scripts/compare_pose.py \
        --new phase9b-out/ce32d556ba1399b9dd5000f9a079475ca33377a9280cf30619a566ff8e9523c3.rawpose.npz \
        --reference data/precomputed_pose/ce32d556ba1399b9dd5000f9a079475ca33377a9280cf30619a566ff8e9523c3.rawpose.npz \
        --video test_videos/public/front_crawl_underwater.webm --out phase9b-out/comparison.json

After the first build, copy the two SHA-256 values the build log prints into
`analysis/pose/manifest.py` (the detector's hash is not published and gets pinned here).

## 7. What the run must produce

`acceptance.json` (also printed as one `ACCEPTANCE_REPORT` log line) with, mapped to the
required outcomes:

| # | Outcome | Where it shows |
| --- | --- | --- |
| 1, 2 | Real YOLO11m and RTMW-x loaded | `preflight.ok`, `preflight.files` (both verified against the manifest), `preflight.smoke_test` |
| 3 | CUDA active | `preflight.providers` contains `CUDAExecutionProvider`; otherwise exit 5 |
| 4 | Video decoded | `run.frames` = 328, `run.video_seconds` = 13.12 |
| 5, 6 | Detector and pose ran on the frames | `run.detector_s_per_frame`, `run.pose_s_per_frame`, `analysis` |
| 7 | A new RawPose | `<sha256>.rawpose.npz` in the bucket |
| 8 | Video SHA-256 matches | checked before the run and again on the RawPose; mismatch is exit 4 |
| 9 | Model identifiers and checksums | `models.detector`, `models.pose`, `models.config`; library versions in `preflight.versions` |
| 10 | Comparison with the Phase 1 reference | `comparison.json` from `compare_pose.py` |
| 11 | Run time and peak memory | `model_load_s`, `run.inference_s`, `run.frames_per_second`, `run.peak_process_memory_mb`, `run.peak_gpu_memory_mb` |
| 12 | Actual billed usage | the project's billing report the next day (not in the file) |
| 13 | Shut down and cleaned up | `phase9b.sh cleanup`, `verify`, billing unlinked, project deleted |

`real_inference` is `true` in the report only when the real model source ran.

## 8. Expected comparison

The same frames, sampling, normalisation and schema as the reference. Differences are
expected from: a new ONNX export (not bit-identical to the Phase 1 one), ONNX Runtime 1.30 on
a GPU against the reference's CPU run, and PyTorch 2.14 against whatever Colab had. The
detector library is the same version as the reference (`ultralytics` 8.4.210).

| Quantity | Tolerance |
| --- | --- |
| Frames | identical (328) |
| Frames with a swimmer box | within 2 percentage points (reference: 100%) |
| Median box overlap | at least 0.90 |
| Confident body joints | median up to 3 px, 95th percentile up to 12 px |
| Median raw score | within 0.5 |
| Same side of the 3.0 cut-off | at least 95% |
| Analysis | same tracking grade (good); every metric the same status and within 5% (reference: stroke rate 23.9 per minute, body line 8.4 degrees) |

These tolerances are first guesses, fixed before the run so they cannot be fitted to it.
Thresholds, the model configuration and the reference outputs are not changed to make the
result look better.

## 9. Success and failure

**Success** (all of): exit 0; `preflight.ok`; the GPU provider active; 328 frames; the
RawPose validates against the video; `compare_pose.py` says "within tolerance".

**Partial** (real inference happened, to be explained, not a failure to hide): the run
completes and `compare_pose.py` says "differences to explain". The differences are reported
as they are, with the versions on both sides.

**Failure**, and what it means:

| Exit | Meaning | Next |
| --- | --- | --- |
| 3 | models missing, altered, or not the expected ONNX contract | a build problem; fix the image, rebuild (counts against the limits) |
| 5 | the GPU is not in use | the CUDA libraries did not load; the one real compatibility risk (section 10) |
| 4 | the video could not be fetched or is not the expected file | network or source change; nothing ran |
| 1 with "not comparable" | the pose is not of the same video or sampling | a bug; stop |
| job timeout | more than 15 minutes | stop; do not raise the limit without a new decision |
| build fails | a pinned package no longer installs | fix the pin, one more build |

Stop conditions: the fifth execution, a second failed build, any budget alert, or anything
not understood. Then `stop`, `cleanup`, and report.

## 10. Not verified until this runs

1. That the image builds: the export tool chain (PyTorch 2.5.1 CPU, mmpose 1.3.2,
   mmdet 3.3.0, mmcv-lite 2.1.0, `numpy<2`) installing together today.
2. That `onnxruntime-gpu` 1.30 and PyTorch 2.14 load the same CUDA 13 / cuDNN 9 pip libraries
   on Cloud Run's driver (580.x). The versions were chosen from ONNX Runtime's and Google's
   published requirements; they have never been run together by us.
3. That the L4 quota is granted to a new project on first deployment.
4. Image size and pull time; cold-start time; frames per second; memory.
5. That the new ONNX export matches the reference within the tolerances.
6. The exact form of the detector's hash (pinned at the first build).

## 11. Emergency stop

    bash worker/phase9b.sh stop                       # cancel executions, delete the job
    gcloud builds list --ongoing --project $PROJECT_ID
    gcloud builds cancel BUILD_ID --project $PROJECT_ID
    gcloud billing projects unlink $PROJECT_ID        # stops every billable resource at once

Unlinking billing is the one command that stops everything; Google warns that resources may
then be removed, which is the intent here.

## 12. Clean-up and proof

    bash worker/phase9b.sh cleanup        # job, image repository, both buckets
    bash worker/phase9b.sh verify         # lists what is left: expect nothing
    gcloud billing projects unlink $PROJECT_ID
    gcloud projects delete $PROJECT_ID    # 30-day recovery period, then permanent

Then: the next day and again after a week, open Billing, Reports, filter on the project, and
record the total. That figure, not this document, is the cost of the test. Delete
`phase9b-out/` from Cloud Shell; keep the copy on the Mac untracked.

## 13. Restrictions that stay in force

No Firebase, no user or student data, no private video; no push to GitHub; no staging or
production deployment; no OpenAI call; the weights are never downloaded to the Mac, never
committed and never redistributed; the image and everything else is deleted after the test.
A successful run proves the models run in the worker on one clip. It does not prove
accuracy, licence clearance, or readiness for users, and stage 2 (the worker against a
Firebase project) is a separate decision.
