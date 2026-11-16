# AquaTrack — project instructions

Condensed from the owner's requirements (2026-11-15). If this file and a newer instruction
from the owner disagree, the owner's instruction wins; then update this file.

## Product

AquaTrack is a personalized swimming feedback web app. A swimmer uploads a video; the app
analyzes posture and movement, finds that swimmer's technique issues, explains up to three
improvement priorities with next-video checkpoints, keeps video and record history, and
tracks how the stroke changes over time. It does not compare everyone to one ideal posture:
it uses the swimmer's level, goals, records, history and own movement patterns.

- The only user is the individual swimmer. Do not build coach or instructor accounts,
  dashboards, account linking, athlete or team management, assigned workouts, approval
  flows or coach-specific screens. AI text may sound like coaching but must never imply a
  human coach reviewed the swim.
- Posture analysis and improvement priorities are the main product value; personalized
  training schedules and the calendar stay on the roadmap as a supporting feature (Phase 6).
- Priorities, in order: (1) posture analysis, (2) personalized issue detection,
  (3) improvement priorities and correction guidance, (4) video and performance history,
  (5) stroke optimization over time, (6) training recommendations and schedules.
  Item 6 supports 1–5 and is driven by analysis results; never a generic workout planner.
- The Project Overview PDF in `docs/` is the functional reference. It is private (personal
  information): never commit it or quote personal details from it.
- The interface stays in English with consistent terminology. No i18n work for now.

## Architecture

- `frontend/`: Next.js (App Router) + Tailwind. Read `frontend/AGENTS.md` before editing.
- `src/aquatrack/contracts.py`: versioned Pydantic contracts (ModelConfig, RawPose,
  ProcessedPose, QualityReport, AnalysisResult, Metric, AnalysisCoverage, AnalysisJobStatus).
  Pose files use `SCHEMA_VERSION`, analysis results `ANALYSIS_SCHEMA_VERSION` (1.2). Only add
  fields within a major version, never rewrite stored results, and keep older documents
  readable; `frontend/app/lib/analysisV1.ts` mirrors them (pure parser, tested with `npm test`).
- `src/aquatrack/api/`: FastAPI. `main.py` (routes), `jobs.py` (the job queue: the video
  documents themselves, claimed in a transaction with a lease, heartbeats, recovery,
  cancel, timeout; `Worker` loop), `store.py` (Firestore/Storage; refuses a real project
  unless the environment says so), `config.py` (`AQUATRACK_ENV`, `validate()`), `limits.py`
  (per-swimmer request limits, in memory), `account.py` (account deletion and the guard that
  refuses new work during it). `src/aquatrack/worker.py`: the worker as its own process
  (`python -m aquatrack.worker`). Docs: `docs/ANALYSIS_JOBS.md`, `docs/SECURITY_REVIEW.md`,
  `docs/DATA_LIFECYCLE.md`, `docs/DEPLOYMENT_PLAN.md`, `docs/RELEASE_PLAN.md`,
  `docs/IMPLEMENTATION_STATUS.md` (update the status document when a feature's state changes).
- `src/aquatrack/analysis/`: `pose/sources.py` (precomputed / local / remote pose sources),
  `pose/rtmw_backend.py`, `pose/cleanup.py`, `processing.py`, `quality.py` (tracking grade
  only), `metrics/cycles.py` (pulls and cycles from mid-pull events), `usability.py` (camera
  side, usable arm points), `biomechanics.py` (metrics with per-metric reliability),
  `metrics/technique.py` (geometry reused by `biomechanics`), `pipeline.py`. Docs:
  `docs/POSE_PROCESSING.md`, `docs/BIOMECHANICS_METRICS.md` (metric specification; update it
  with any metric or threshold change), `docs/PHASE2_VALIDATION.md`.
- `src/aquatrack/analysis/interpretation.py`: reads a stored AnalysisResult plus the
  swimmer's profile and earlier analyses, writes an `Interpretation`
  (`videos/{id}/interpretations/{id}`, a new document per run). No pose data or model needed;
  `POST /videos/{id}/interpret` runs it again. Rules and thresholds:
  `docs/INTERPRETATION_RULES.md` (update it with any rule change and bump `RULES_VERSION`).
- `src/aquatrack/analysis/feedback.py` + `explain.py` + `src/aquatrack/evidence.py`: feedback,
  next-video checkpoints, references and the optional, validated LLM rewording
  (`videos/{id}/feedback/{id}`). The LLM provider is OpenAI (official SDK, Responses API,
  strict JSON schema, default model `gpt-6-luna`), behind `explain.Explainer`; off unless
  `AQUATRACK_LLM_PROVIDER=openai` and `OPENAI_API_KEY` are both set in the backend
  environment. Never call the paid API without the owner's approval, never ask the owner to
  paste a key, and check OpenAI's documentation before changing SDK calls or model names. Docs: `docs/FEEDBACK.md`, `docs/EVIDENCE_LIBRARY.md`.
- Profile (`profiles/{uid}`): optional `goals`, `primary_goal`, `target`, `weak_note`; the
  free-text note is never analysed or sent to a model.
- `src/aquatrack/training/`: `library.py` (curated activities and their checked sources;
  bump `LIBRARY_VERSION` on any change), `planner.py` (deterministic single-session and
  7-day plans), `models.py` (contracts, `TRAINING_VERSION`), `explain.py` (checks on optional
  plan rewording). `src/aquatrack/api/training.py`: plans, sessions, calendar, edit rules,
  ownership (`training_plans/{id}`, `training_sessions/{id}`: owner read, backend-only
  writes). Every session has a `revision`; edits name the one they were made from and are
  written with a compare-and-set (`store.swap_doc`), a plan is saved only with its preview's
  `token`, and a session keeps its original slot (`planned_date`) when moved. Doc:
  `docs/TRAINING.md` (update it with any activity, rule or threshold change).
- `src/aquatrack/analysis/comparison.py`: session comparison (per metric, neutral states),
  progress series, checkpoint follow-up. Computed from stored analyses on request, never
  stored. APIs: `GET /videos/{a}/compare/{b}`, `GET /progress`, `DELETE /videos/{id}`
  (backend deletes everything for a video; clients can never delete directly). Doc:
  `docs/HISTORY_AND_DELETION.md`.
- Firebase: Auth, Firestore, Storage; rules in `firebase/`. Videos are uploaded by the web
  app straight to Storage; the API never receives files. Results: Firestore
  `videos/{id}/analyses/{analysisId}`, arrays in Storage `analysis/{uid}/...` (backend-only
  writes, owner-only reads).
- Module boundaries: video ingestion → pose inference → temporal processing → metrics →
  issue interpretation → explanation → training recommendations → persistence, with
  versioned structured contracts between them. Analysis runs as a background job with
  status, errors and retries; never inside a web request.
- Inference sits behind one interface with three interchangeable sources that all produce
  the same validated data structure: precomputed pose data from Colab, local model
  inference, and (later) a dedicated worker or GPU service. `precomputed` is a development
  fixture: it is never real inference and must never be described as such. Model inference
  on a new upload inside the worker has not been run; do not claim it until one real video
  has gone through `AQUATRACK_POSE_SOURCE=local` on a real worker.
- Planned production: Render (frontend and API) + Firebase; a GPU service only if measured
  need. Nothing is deployed yet.

## Measurement and evidence rules

- Measured, never invented. Insufficient data means "Not measurable" plus the reason.
  An honest incomplete analysis beats a complete-looking wrong one.
- Example or mock values must be visibly labelled (`ExampleNote`, "Example" badge) until the
  screen shows real analysis output. Never remove those labels while mock data remains.
- Raw model output is stored separately from cleaned data, with frame, timestamp, box,
  confidences and model versions. Estimated points stay flagged with reduced confidence.
  Interpolate short gaps only; never across long occlusions or a change of swimmer.
- A model score is not visibility. Arm geometry is read only from the camera-side arm inside
  an underwater pull that was followed; points the model draws during the recovery or behind
  the body are reported as not verified and never measured. Every metric carries its own
  status (reliable / limited / unavailable), evidence and limits; the tracking grade never
  vouches for a metric.
- A metric is not a technique problem. Interpretation (`analysis/interpretation.py`) keeps
  three levels apart: observations, issue candidates, priorities (at most three, often
  none). No ideal angles, no technique score, no comparison with other swimmers: only the
  swimmer's own cycles and their own compatible earlier swims. Rules needing an outside norm
  stay `pending_validation` until a source is verified. Limited or unavailable metrics, arm
  metrics and anything measured under a changing camera view never trigger an issue.
  Measurement limits are reported apart from findings and are never technique faults.
  Missing evidence, missing history or a missing profile must never be filled in.
- Feedback (`analysis/feedback.py`) keeps five categories apart: observation, focus,
  priority, education (general information for a goal the swimmer chose: never about their
  video, never ranked) and insufficient. It never creates a finding; goals only add education
  and affect ranking. Choosing a goal never makes something measurable.
- Evidence (`evidence.py`): a source enters only after its DOI resolves at Crossref with a
  matching title and its abstract has been read; claims say no more than the abstract.
  Findings, research-supported suggestions, engineering heuristics and unverified hypotheses
  are labelled as such. A paper discussing a technique does not validate a metric or switch on
  a rule. Bump `EVIDENCE_VERSION` on any change and update `docs/EVIDENCE_LIBRARY.md`.
- Comparing sessions: a change in a number is not an improvement. Use only "increased",
  "decreased", "no clearly measurable change", "insufficient evidence", "not comparable";
  never colour one direction as good. Never put incompatible sessions (stroke, filming angle,
  distance, effort, metric definition) on one line, never interpolate, never compare a sprint
  with an easy swim. Times typed in by the swimmer are labelled as theirs and never linked to
  a technique measurement. Synthetic history is for tests and must be labelled as such.
- Training: a recommendation is analysis-based only when a stored, supported finding (a focus
  or priority whose rule is mapped in `planner.RULE_ACTIVITIES`) backs it; otherwise it is
  goal-based or general and must say that no problem was found. Never invent a weakness to
  personalise a plan. Activities come only from the curated library; an activity is called
  research-supported or coaching guidance only where its source was actually read, and
  durations, repeats and paces are labelled as AquaTrack's own conservative choices. Never
  exceed the swimmer's stated days, frequency or session time, never raise the load
  automatically, never mark a session completed for the swimmer, never overwrite an edited
  plan silently, and never read adherence as technique improvement or as the cause of a
  measured change. What the swimmer typed in (notes, own activities) is never sent to a model.
- Metrics and issue detection are deterministic, tested and independent of any LLM.
  Report an issue only with enough measured evidence; "no clear issue" is a valid result.
- The LLM only rewords validated findings. Send it structured metrics, never videos, names
  or emails. Reject output containing numbers, issues or references that were not in its
  input. The app must stay useful when the LLM API is unavailable.
- Scientific references are used only after verifying title, authors, year, DOI/URL,
  population and limitations. Never cite from memory. Do not apply elite-adult findings to
  beginners or young swimmers without saying so. Correlation is never stated as causation.
- No unsafe training advice: breath-holding drills, excessive volume, performance promises.

## Models (evidence: `experiments/detector_comparison/results/REPORT_ko.md`)

- Detector: `yolo11m.pt` (pretrained), imgsz 640, conf 0.15, track-based swimmer selection
  with the existing `BoxTracker`. Configurable alternatives: `yolo11x.pt` @640,
  student's `swim_pose.pt` @1280 (above-water, provisional).
- Pose: stock RTMW-x 384x288 (`rtmw_x_stock.onnx`, 133 points) via `RtmwEstimator`. It is an
  ONNX export of the public OpenMMLab cocktail14 checkpoint (`...-f840f204_20231122.pth`);
  OpenMMLab ships no ONNX for it. The official cocktail13 ONNX is NOT a drop-in replacement
  (different score scale; cleanup's 3.0 cut-off would reject everything). See
  `docs/POSE_PROCESSING.md`.
- Supported now: freestyle, underwater side view. Above-water footage is limited and must be
  quality-gated. Other views and strokes are not supported yet.
- Keep models and thresholds configurable and record them with every analysis result.
- Model research is closed: no training, fine-tuning or broad comparisons unless a critical
  blocker requires it and the owner agrees.

## Environment, privacy and data

- This Mac is for code, light tests and result analysis. No heavy inference here and no
  large weight or dataset downloads. Heavy inference runs in the student's Google Colab;
  weights live in the student's Google Drive. Colab is never a production backend.
- Firebase: Emulator Suite only for now. `.claude/launch.json` has the configs
  (`firebase-emulators`, `backend-emulated`, `frontend-emulated`);
  `frontend/scripts/emulators.mjs` picks an installed JDK 21+ for the emulators by itself. Do not connect to, read or change any production
  Firebase project, and do not create service-account keys.
- Uploaded videos and pose data are private user data and may show minors. Per-user access
  only; no file paths or internals in user-facing errors; nothing sensitive in logs. Users
  can delete their own videos (backend deletion, emulator-tested). Still release blockers: a
  durable deletion queue, account deletion, backups and retention, and legal review.
- Keep `experiments/` local and untracked. Never commit notebooks or scripts that contain
  Google Drive file IDs or sharing links.
- Never commit weights, datasets, videos, pose dumps, private documents, `.env` files,
  credentials or `.DS_Store`. `.gitignore` covers these; check `git status` before commits.
- Do not purchase or enable paid services without approval.
- Licensing is unresolved and blocks a hosted launch: Ultralytics YOLO11 is AGPL-3.0 (or a
  paid Enterprise licence); the RTMW weights were trained partly on a non-commercial dataset;
  the repository has no LICENSE file. See `docs/RELEASE_PLAN.md`. Do not add a licence file
  or swap a model without the owner's decision.
- Environments: `AQUATRACK_ENV` is `emulator` locally. Never set `staging` or `production`,
  `AQUATRACK_ALLOW_PRODUCTION_FIREBASE`, or service-account credentials on this machine.

## Git

- Work on `feature/aquatrack-completion`. Never change `main`. No rebase, no force-push.
  Integrate by merging; keep the student's history and research branches intact.
- Commits use the repository's configured identity (the student's, with authorization).
- Ask before commits (other than merges already approved for a phase), pushes, destructive
  operations, paid resources and deployment. Stop if an operation risks data loss.

## Roadmap

0. Repository integration and preparation (done locally 2026-11-15, not pushed).
1. Models, pose quality pipeline, and the minimum upload → job → result flow using
   precomputed pose data (done, local commit `6aa3852`, not pushed). Pose files for the
   public test clips: `data/precomputed_pose/` (ignored).
2. Biomechanics metrics (freestyle, underwater side view first), shown through that flow
   (done, local commit `1357fba`, not pushed). Manual annotations and check scripts: `experiments/phase2_validation/`.
3. Personalized pattern and issue detection. On the two real clips it yields observations
   and no issues, which is the intended result for that evidence.
   (Phase 3 done, local commit `c0e482e`, not pushed.)
4. Feedback, checkpoints, verified evidence, LLM layer (done, local commit `4e46baa`, not
   pushed; the LLM path is tested with mocks only and no interpretation rule was activated).
5. History, comparison, progress, checkpoint follow-up and video deletion (done, local commit
   `5beb945`, not pushed; comparison logic exercised on labelled synthetic sessions only,
   since no real swimmer has two comparable sessions yet).
6. Training recommendations, plans, calendar and the OpenAI adapter (done, local commit
   `1a9e02c`, not pushed; analysis-based plans exercised with synthetic findings only; no
   paid API call made).
7. Pre-deployment readiness: durable job queue and worker, edit-conflict protection,
   account deletion, request limits, environment checks, browser journeys, security review,
   deployment and release plans (implemented locally 2026-11-16, uncommitted, awaiting the
   owner's review). Not a launch: production inference, licensing, legal review and a real
   Firebase project are open blockers (`docs/IMPLEMENTATION_STATUS.md`, section 3).
8. Not defined yet. Nothing is deployed and nothing is pushed.

One working end-to-end flow comes before breadth of metrics. Do not start a phase without
the owner's approval. After each phase, stop and report.

## Testing and status claims

- Before reporting: `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .`,
  and in `frontend/`: `npm run lint`, `npx tsc --noEmit`, `npm test`, `npm run build`. If
  something could not be run, say why.
  `tests/test_emulator_rules.py` and `tests/test_emulator_backend.py` only run when the
  emulators are up (`npm --prefix frontend run emulators`); say whether they ran or were
  skipped. Browser journeys: `npm run e2e` in `frontend/` (Playwright with the installed
  Chrome; needs the emulators, API and dev server, which it starts or reuses).
- Orchestration tests use fake inference adapters and say so; tests on saved model output
  are a development fixture. Neither counts as inference on a new video.
- Synthetic or mocked tests never count as real-video validation. Report the two separately.
- For every feature say which apply: implemented / tested / verified with real data /
  incomplete / blocked / not yet scientifically validated. Source code or UI existing is not
  verification.

## Reports to the owner

- Written in Korean, given in full in the conversation (not only as a file path), inside
  ONE plain-text code block so it can be copied. Numbered sections, short paragraphs, no
  Markdown tables, no decoration. Include real commands, errors, test results and commit
  hashes. Separate completed work, incomplete work, blockers and next actions.
- Enough detail for an outside technical reviewer; say what is verified and what is assumed;
  list incomplete work and blockers explicitly; mention any report files separately.
- Phase reports are titled "AquaTrack — Phase X Completion Report". Use the section list the
  owner gave for that phase. Default (Phase 1 onward): 1 작업 개요, 2 완료된 작업,
  3 변경된 파일 및 구현 내용, 4 테스트 및 검증 결과, 5 테스트 영상 출처 및 라이선스,
  6 실제 영상 기반 분석 검증 결과, 7 발견된 문제 및 제한사항, 8 Git 상태 및 커밋 정보,
  9 다음 Phase 개발 제안, 10 사용자 승인 또는 설정이 필요한 사항.
