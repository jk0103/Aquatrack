# Deployment plan (for approval; nothing is deployed)

**Scope (owner's decision, 2026-11-16):** AquaTrack is permanently a free, noncommercial
student research and educational project. This plan is about what it would cost and take to
test and, if approved, run that free project. There is no commercial launch, no paid tier
and no revenue in it. Small infrastructure costs are possible only when the owner approves
each one.

Prepared 2026-11-16. Nothing here has been created, bought or configured. Prices were read
on the providers' own pages on that date; many were read through an automated page fetch, so
**re-open the linked page before putting a number in a budget**. Three kinds of figure are
kept apart: **confirmed** (stated on the page), **derived** (arithmetic on confirmed
figures) and **assumed** (our own guess, unmeasured).

## 1. Topology

| Part | Proposed home | Why |
| --- | --- | --- |
| Next.js frontend | Render web service | official Next.js guide; simple; no GPU needed |
| FastAPI API (queues, reads, training, validation) | Render web service | official FastAPI guide; holds the OpenAI key; never runs inference |
| Auth, Firestore, Storage | Firebase (Blaze plan) | already the app's data layer |
| Job queue | Firestore (the video documents) | no extra service; `docs/ANALYSIS_JOBS.md` |
| Pose inference worker | a GPU host that scales to zero (section 3) | Render has no GPU; CPU is too slow |
| Rewording | OpenAI API, optional, off by default | `docs/OPENAI_LIVE_TEST.md` |

## 2. Render for the frontend and API

Confirmed (https://render.com/pricing, https://render.com/docs/free, /docs/disks,
/docs/deploy-nextjs-app, /docs/deploy-fastapi):

- Instance prices per month: 0.5 CPU / 512 MB $7; 1 CPU / 2 GB $25; 2 CPU / 4 GB $85;
  4 CPU / 8 GB $175; larger sizes up to 12 CPU / 96 GB. Billing is prorated to the second.
  Workspace plans: Hobby $0, Pro $25/month, plus compute.
- Free web services spin down after 15 minutes without traffic, have 512 MB, and 750 free
  instance hours a month per workspace. Background workers have no free tier.
- Persistent disks: $0.25 per GB per month, one instance only.
- **No GPU instance appears anywhere on the pricing page or in the web-service and worker
  docs.** No Render page was found that says so in one sentence; a Render article (February
  2026) advises sending heavy inference to GPU clouds.

Assessment: suitable for the frontend and the API. Two instances, each $7 (512 MB) or $25
(2 GB) a month. The API with its Python dependencies (OpenCV, NumPy, Firebase Admin) is
**assumed** to need the 2 GB size; measure before choosing. Not suitable for the pose worker.

Why not run inference on a Render CPU instance: measured in Colab on CPU, the pipeline took
about 1.8 s per frame. A 30-second clip at 25 fps is 750 frames, about 22 minutes
(derived). A 4 CPU / 8 GB instance at $175/month running flat out would manage roughly 64
such clips a day (derived, **assuming** Render's CPUs match Colab's, which is unmeasured),
and costs $175 whether or not anyone uploads.

## 3. Inference worker: options

What the worker needs: a container with the Python `pose` extra, the two weight files (about
40 MB and 370 MB), ONNX Runtime with CUDA, a GPU with a few GB of memory (**assumed** from
model size; unmeasured), access to Firebase, and no public endpoint. GPU throughput for this
pipeline has **never been measured**; every cost per video below rests on an assumed speed.

| Option | Confirmed price | Scale to zero | Notes |
| --- | --- | --- | --- |
| Google Cloud Run with GPU | L4 $0.0001867/s, CPU $0.000018/vCPU-s, memory $0.000002/GiB-s (us-central1); minimum 4 vCPU and 16 GiB with an L4; billed for the instance lifetime, 1 minute minimum | yes | Only L4 and a larger card; L4 regions listed: us-central1, us-east4, europe-west1, europe-west4, asia-southeast1 (asia-south1 by invitation); none in Korea or Japan. Same cloud as Firebase: the worker can use a service account without exported keys. Docs say instances start in about 5 s before the app loads its models. Sources: docs.cloud.google.com/run/docs/configuring/services/gpu, cloud.google.com/run/pricing |
| Modal | T4 $0.000164/s, L4 $0.000222/s, plus CPU $0.0000131 per core-second and memory $0.00000222 per GiB-second; Starter plan $0 with $30 monthly credit | yes | Idle window before shutdown defaults to 60 s (billed). Security page: SOC 2 Type II; function inputs and outputs kept up to 7 days. The worker would fetch the video from Storage itself, so the video is not a function input. A third data processor. Source: modal.com/pricing, modal.com/docs/guide/security |
| RunPod Serverless | 16 GB class $0.58/hour, 24 GB class $0.75/hour as fetched (flex or active rate not confirmed) | yes | Billed during cold start; 5 s default idle timeout. Compliance and data handling not verified. Source: runpod.io/pricing |
| Compute Engine VM with an L4 (`g2-standard-4`) | $0.7068/hour (us-central1, on-demand) | no | Bills while running: about $516 a month if left on (derived). Needs start/stop automation to be economical |
| Render CPU instance | 4 CPU / 8 GB $175/month | no | see section 2 |

Cost per video (derived from the confirmed rates, on **assumed** speeds):

| Assumption | Cloud Run L4 (4 vCPU, 16 GiB: $0.000291/s) | Modal T4 (2 cores, 8 GiB: about $0.000208/s) |
| --- | --- | --- |
| 750 frames at 10 frames/s + 60 s start-up and model load = 135 s | about $0.039 | about $0.028, or about $0.041 with the 60 s idle window |
| 750 frames at 30 frames/s + 60 s = 85 s | about $0.025 | about $0.018 (+ idle window) |
| For comparison: Colab-speed CPU, 1,350 s on a $175/month instance | fixed cost; $1.75 a video at 100 videos a month | |

At 100 videos a month that is roughly $3 to $5 on a scale-to-zero GPU, at 1,000 roughly $25
to $45, against a fixed $175 or more for an always-on machine. **These are estimates until
one real run measures frames per second, start-up time and memory.**

### Recommendation

1. **Cloud Run with an L4 GPU, run as a job per video (`python -m aquatrack.worker --once`)
   or as a worker that polls while there is work.** Reasons: private data stays inside
   Google Cloud next to Firebase, access by service account with no key files, scale to
   zero, per-second billing. Costs more per second than a T4 elsewhere and has no region
   near Korea.
2. **Modal with a T4** as the cheaper alternative and the easiest first measurement (the
   Starter plan's monthly credit would likely cover a pilot). Adds a data processor.
3. Not recommended: CPU inference on Render (slow, fixed cost); an always-on GPU VM (idle
   cost); a student's Colab or Drive (never production).

The model stays the same. No smaller or different model is proposed here; changing models
because one is easier to host would throw away the validation done so far.

The first controlled run, its tolerances and its budget: `docs/GPU_ACCEPTANCE_TEST.md`.

## 4. Monthly cost of running the free project at small scale (estimate)

Paid by the project's owner; nothing is recovered from users.

| Item | Monthly | Basis |
| --- | --- | --- |
| Render frontend | $7 to $25 | confirmed instance prices |
| Render API | $7 to $25 | confirmed instance prices; size assumed |
| Render workspace | $0 (Hobby) | confirmed |
| Firebase Blaze | about $0 to $5 | Firestore free quota 50,000 reads, 20,000 writes a day and 1 GiB (confirmed); Storage about $0.02 to $0.026 per GB-month (confirmed for us-central1 / legacy buckets); 20 GB of video is about $0.50 (derived). Storage now requires the Blaze plan (confirmed) |
| Inference, 100 to 1,000 videos | $3 to $45 | section 3, assumed speed |
| OpenAI rewording, if enabled | under $1 | at most about $0.003 a call (derived from list price and the output bound) |
| **Total** | **about $20 to $100** | excludes a domain and monitoring. No licence fee is planned |

Not verified: Cloud Storage internet egress for the new bucket type, prices outside US
regions, Ultralytics Enterprise price, RunPod per-second and compliance details, Render's
plan-level compliance offerings.

## 5. Costs and blockers that are not hosting

- **Ultralytics YOLO11 licence.** AGPL-3.0, or a paid licence. Ultralytics states that
  using YOLO behind a hosted service needs one or the other, **whether or not the service
  is free**. For a free student project the fitting route is publishing the whole project
  under AGPL-3.0, which needs contributor rights confirmed and the owner's explicit
  approval; replacing the detector is the contingency; a paid licence is not an objective.
- **RTMW weights.** Code is Apache-2.0; the checkpoint has no stated terms and was trained
  on a mix that includes research-only and noncommercial datasets. A noncommercial project
  is within the wording of those restrictions, but nobody has confirmed that for the
  checkpoint, and a free public application should ideally have a written answer first.
- Details, the three uses checked separately, and the inquiry drafts:
  `docs/MODEL_LICENSING_DECISION.md`.

## 6. Environments

| Environment | `AQUATRACK_ENV` | Firebase | Worker | Pose source |
| --- | --- | --- | --- | --- |
| Local development | `emulator` (default) | Emulator Suite, project `demo-aquatrack` | embedded thread | `precomputed` fixture |
| Automated tests | `test` or unset | in-memory store, or the emulators | inline | fake adapters, saved pose |
| Staging (future) | `staging` | a separate real project | external | `local` |
| Production (future) | `production` | the live project | external (required) | `local` (required) |

`aquatrack.api.config.validate()` runs at API start, in `/health/ready` and before the worker
starts. It refuses, among other things: service-account credentials or a non-`demo-` project
in a local environment; emulator hosts in a real one; a real project without both
`AQUATRACK_ENV` and `AQUATRACK_ALLOW_PRODUCTION_FIREBASE=1`; production with the precomputed
fixture or an embedded worker. The Firestore store itself also refuses a real project unless
the environment says so. Messages never include secret values.

Secrets (future): `OPENAI_API_KEY` and the service account live in the host's secret store
(Render environment groups; Google Secret Manager or the attached service account for the
worker). Nothing secret has a `NEXT_PUBLIC_` name; the frontend only holds the Firebase web
configuration, which is public by design.

## 7. Deployment steps (after approval; none taken)

1. Decide the licensing questions in section 5.
2. Create a staging Firebase project; deploy the rules; enable Auth; set the region.
3. Build the worker image with weights from their public sources; run **one real video**
   through it; compare with the saved results; measure speed, memory and start-up.
4. Deploy API and frontend to Render against staging; restrict CORS; set secrets.
5. Run the browser journeys against staging with a disposable account.
6. Decide retention, backups and legal texts (`docs/DATA_LIFECYCLE.md`).
7. Only then create production, with the same steps and a rollback plan.

Health checks: `GET /health` (liveness, for the platform), `GET /health/ready` (configuration
valid, queue readable, job counts). Worker start-up, recovery and failure handling:
`docs/ANALYSIS_JOBS.md`, section 4.

Rollback: Render keeps previous deploys and can redeploy one; Firestore rules are versioned
in `firebase/`; stored documents are only ever added to within a schema version, so an older
API can read newer documents. Data rollback needs the backups in `docs/DATA_LIFECYCLE.md`.
