# Real-inference acceptance test: hosts, procedure, budget

**Nothing here has been run and no cloud resource exists.** This is the plan for the first
real run of YOLO11m and RTMW-x in the AquaTrack worker, for the owner's approval.

Figures marked **published** were read on the provider's own pages on 2026-11-16;
**derived** is arithmetic on those; **assumed** is unmeasured. Speed on a GPU has never been
measured: the only measurement is about 1.8 s per frame on a Colab CPU (Phase 1).

## 1. Cloud Run GPU and Modal

| | Google Cloud Run (job) | Modal |
| --- | --- | --- |
| GPUs (published) | NVIDIA L4, 24 GB; RTX PRO 6000, 96 GB. One per instance | T4, L4, A10, L40S, A100, H100 and others |
| Regions (published) | L4: us-central1, us-east4, europe-west1, europe-west4, asia-southeast1 (asia-south1 by invitation). **None in Korea or Japan** | runs across several clouds worldwide unless pinned; pinning costs 1.15x (broad) or 1.75x (narrow) |
| Minimum resources (published) | 4 vCPU and 16 GiB with an L4; at most 8 vCPU, 32 GiB | from 0.125 core; memory as requested |
| Disk (published) | in-memory filesystem: temp files use RAM | not verified |
| Start-up (published) | instance with drivers in about 5 s, before the image pull and model load | container boot about 1 s; time to warm "seconds to minutes" |
| Scale to zero (published) | a job runs and exits; billed for its lifetime, 1 minute minimum | yes; an idle window (default 60 s, settable from 2 s) is billed |
| Time limit (published) | GPU job task: up to 12 hours | function: default 300 s, up to 24 hours |
| Concurrency (published) | parallelism up to the GPU quota; a new project gets 3 L4 automatically | Starter plan: 10 GPUs at once |
| Interruption (published) | GPU tasks are terminated for maintenance, not migrated | functions are preemptible; non-preemptible GPU is not offered |
| Model loading (published) | in-image recommended under 10 GB; or a Cloud Storage mount | Volume or in-image, similar performance |
| Firebase access | attached service account, no key file (published: never set a credentials file) | a service-account key stored as a Secret (published), kept in the US; keyless OIDC federation to Google is named as possible but has no documented walkthrough |
| Storage access | same cloud; same-region transfer free (published) | over the internet from wherever the container runs |
| Logs (published) | Cloud Logging, 30 days, first 50 GiB a month free | 1 day on Starter, 30 on Team |
| Data handling (published) | inside the project's own Google Cloud | SOC 2 Type II; DPA on its Trust Center; inputs and outputs kept up to 7 days; logs, secrets, images stored in the US |
| Price per second (published) | L4 $0.0001867, vCPU $0.000018, GiB $0.000002 (us-central1; other regions not read) | T4 $0.000164, L4 $0.000222, core $0.0000131, GiB $0.00000222 |
| Smallest configuration (derived) | L4 + 4 vCPU + 16 GiB = $0.0002907/s ($1.05/h) | T4 + 2 cores + 8 GiB = $0.000208/s ($0.75/h); L4 = $0.000266/s ($0.96/h) |
| Idle cost (published) | none for a job | none after the idle window |
| Free allowance (published) | 240,000 vCPU-s and 450,000 GiB-s a month; none for GPU; $300 credit for new customers | $30 a month on Starter; a payment method is required |
| Spend control (published) | budgets and alerts; a spend cap pauses Cloud Run | workspace spend limit on every plan |
| Operational effort (assessment) | a Google Cloud project, billing, Artifact Registry, IAM, a build | an account, a token, one Python file |
| Container (assessment) | our Dockerfile as it is | our Dockerfile through Modal's image builder; not verified |

### Cost per video (derived from published prices on assumed speeds)

GPU throughput is the unknown. Two assumed speeds, plus an assumed 60 s for image start and
model load, billed on both hosts:

| Case | Frames | Assumed 10 frames/s | Assumed 30 frames/s |
| --- | --- | --- | --- |
| 13 s clip (the reference clip, 328 frames) | 328 | 93 s: Cloud Run $0.027; Modal T4 $0.019 (+$0.012 idle window) | 71 s: $0.021; $0.015 (+$0.012) |
| 30 s video at 25 fps | 750 | 135 s: $0.039; $0.028 (+$0.012) | 85 s: $0.025; $0.018 (+$0.012) |
| 100 videos a month (30 s each, one start each) | | about $3.90; about $4.00 | about $2.50; about $3.00 |
| 1,000 videos a month | | about $39; about $40 | about $25; about $30 |

For scale, the CPU measurement (1.8 s per frame) would make a 30 s video about 22 minutes:
about $0.39 of the same Cloud Run instance without ever using its GPU.

Caveats: every start bills the image pull and model load (unmeasured; batching several
videos into one `--drain` run shares it); Cloud Run bills at least 60 s per job; Modal bills
its idle window; Cloud Run prices outside us-central1 and internet egress were not read;
the Firebase bucket's location decides whether transfer is free; none of this includes the
API, Firebase, or licences.

### Recommendation: Cloud Run GPU job, L4, us-central1

Not because of price (Modal's T4 is cheaper per second and has a monthly credit), but because:

1. **It is the intended production home.** The test then also answers the questions that
   matter later: does our image run under Cloud Run's driver, does ONNX Runtime get the GPU
   there, does a video fit the in-memory disk, how long is a cold start.
2. **Private videos stay inside the project's own Google Cloud**, next to Firebase, with no
   third processor and no long-lived key.
3. **A job cannot idle.** It runs, exits and stops billing; there is no window to forget.
4. **One place to shut everything down**: a dedicated test project can be deleted whole.

Costs of this choice: more set-up than Modal, no region near Korea (latency of a batch job
does not matter to a swimmer waiting minutes, but data location does and must be decided
before real users), and 16 GiB is the smallest size.

**Fallback: Modal with a T4**, if the Cloud Run GPU quota is not granted or the set-up
stalls. Suitable for stage 1 only (public video, no Firebase), because stage 2 there needs a
service-account key stored with a third party.

## 2. The test

**Stage 1: the models alone (no Firebase, no user data).** One job runs
`scripts/gpu_acceptance.py` in the worker image on the public clip "Front Crawl Underwater"
(Wikimedia Commons; 13 s, 328 frames, 25 fps; the Phase 1 primary clip) with the saved
Phase 1 RawPose as reference.

It demonstrates, for the first time: official weights loaded and verified; real YOLO11m
detection; real RTMW-x inference on a GPU; a new RawPose in the existing schema; the
existing pipeline on it. It records: preflight report, model load time, frames per second
(detector and pose apart), peak process and GPU memory, and from the billing report the
actual cost.

Comparison with the reference, stated before the run:

| Quantity | Tolerance | Why a difference is expected at all |
| --- | --- | --- |
| Frames decoded | identical | same file, same decoder family |
| Frames with a swimmer box | within 2 percentage points | detector on GPU against CPU; `ultralytics` version (reference: 8.4.210) |
| Box overlap (median IoU) | at least 0.90 | the same |
| Confident body joints, distance | median up to 3 px, 95th percentile up to 12 px | a new ONNX export (not bit-identical), ONNX Runtime GPU against CPU arithmetic, a box that moved by a pixel changes the crop |
| Raw score level (median) | within 0.5 | a different model generation would show here (its scale differs) |
| Same side of the 3.0 confidence cut-off | at least 95% of points | the same |
| Metrics of the analysis | same status; values within 5% (or 0.5 absolute) | downstream of all of the above |

Outside tolerance is not a failure to hide: the report lists each difference with the known
reasons (versions, export hash, device). The tolerances are first guesses and will be
revised after one real run. Frame sampling and input normalisation are the same code in
both runs; the result schema is unchanged.

**Stage 2: the worker end to end (needs a staging Firebase project; separate approval).**
Upload the same public clip through the web app, let `python -m aquatrack.worker --drain`
run as a job, and see the result in AquaTrack. Proves: a worker independent of the API,
authorised access to Storage and Firestore, persistence, display. Then one clip the system
has never seen.

Real inference is only claimed after stage 1 has actually run; a new upload analysed
automatically only after stage 2.

## 3. Budget (proposal; nothing is approved)

| Item | Proposal |
| --- | --- |
| Provider | Google Cloud Run, job |
| GPU | 1 x NVIDIA L4, 4 vCPU, 16 GiB, no zonal redundancy |
| Region | us-central1 (published prices; first-time L4 quota granted automatically) |
| Project | a new, dedicated test project with billing, deleted after the test |
| Videos | 1 first (the 13 s reference clip); at most 3 (the three public clips that have saved references) |
| Executions | at most 5 in total, including failed starts |
| Time limit | 15 minutes per execution, enforced by the job's own timeout; 75 minutes in all |
| Expected run time | a few minutes in total (assumed) |
| Expected compute cost | under $0.30 (derived from assumed speeds) |
| Worst-case compute cost | 75 min x $1.05/h = **$1.31** (derived: every execution runs to its limit) |
| Image build | Cloud Build; price not read; expected cents to a few dollars (assumed) |
| Image storage | about 6 GiB at about $0.10 per GiB-month (derived) = cents if deleted the same day |
| Logging, transfer | inside free allowances (published allowances; usage assumed small) |
| **Budget alert** | **$5** |
| **Hard ceiling** | **$10**: stop and report if reached, whatever the state |

Measured cost comes from the project's billing report after the test, not from this table.

### Procedure

1. Owner: create the test project, link billing, set a $5 budget alert. (Needs approval;
   not done.)
2. Enable Cloud Run, Artifact Registry, Cloud Build. Build `worker/Dockerfile` in Cloud Build
   with `ACCEPT_MODEL_TERMS=yes`. Record the two model hashes from the build log into
   `analysis/pose/manifest.py`.
3. Put the public clip and its reference RawPose in a private bucket of the test project.
4. Create the job from `worker/cloudrun-job.yaml`, with the command
   `python scripts/gpu_acceptance.py ...` and the bucket mounted read/write.
5. `gcloud run jobs execute ... --wait`. Read `acceptance.json` and the logs.
6. If the preflight fails: fix, rebuild, re-run, within the execution limit.
7. Write the results into `docs/GPU_ACCEPTANCE_TEST.md` (speed, memory, cost, comparison).

### Failure handling

- Preflight fails (exit 3): nothing was processed; cost is the start-up minute.
- The run exceeds 15 minutes: the job is killed by its timeout; investigate before another.
- GPU quota not granted: stop; use the fallback or request quota. No retry loop.
- Any cost surprise or the alert firing: stop and delete (below).

### Shutdown and proof that nothing is running

1. `gcloud run jobs delete aquatrack-worker` (also ends running executions).
2. Delete the Artifact Registry repository and the test bucket.
3. `gcloud run jobs list` and `gcloud run services list` are empty; no instances under
   Compute Engine.
4. Simplest and complete: **delete the test project** (`gcloud projects delete`), which
   stops all billing for it.
5. The next day, check the billing report for the project: no new charges after shutdown.

## 4. What the test does not show

Accuracy on new swimmers, behaviour under load, cost at volume, licence clearance, or
anything about a production deployment. One clip processed correctly is one clip.
