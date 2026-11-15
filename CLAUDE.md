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
  ProcessedPose, QualityReport, AnalysisResult v1, AnalysisJobStatus). Change them with care
  and bump `SCHEMA_VERSION` on breaking changes; `frontend/app/lib/analysisV1.ts` mirrors them.
- `src/aquatrack/api/`: FastAPI. `main.py` (routes), `jobs.py` (job states, in-process
  runner: not a durable queue), `store.py` (Firestore/Storage; refuses to run without the
  emulators unless explicitly allowed).
- `src/aquatrack/analysis/`: `pose/sources.py` (precomputed / local / remote pose sources),
  `pose/rtmw_backend.py`, `pose/cleanup.py`, `processing.py`, `quality.py`, `pipeline.py`,
  `metrics/cycles.py`, `metrics/technique.py`. Processing rules and thresholds are documented
  in `docs/POSE_PROCESSING.md`.
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
  inference, and (later) a dedicated worker or GPU service.
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
  cannot delete their videos yet: deletion and privacy compliance are release blockers.
- Keep `experiments/` local and untracked. Never commit notebooks or scripts that contain
  Google Drive file IDs or sharing links.
- Never commit weights, datasets, videos, pose dumps, private documents, `.env` files,
  credentials or `.DS_Store`. `.gitignore` covers these; check `git status` before commits.
- Do not purchase or enable paid services without approval.

## Git

- Work on `feature/aquatrack-completion`. Never change `main`. No rebase, no force-push.
  Integrate by merging; keep the student's history and research branches intact.
- Commits use the repository's configured identity (the student's, with authorization).
- Ask before commits (other than merges already approved for a phase), pushes, destructive
  operations, paid resources and deployment. Stop if an operation risks data loss.

## Roadmap

0. Repository integration and preparation (done locally 2026-11-15, not pushed).
1. Models, pose quality pipeline, and the minimum upload → job → result flow using
   precomputed pose data (implemented and validated on real video locally 2026-11-15,
   uncommitted). Pose files for the public test clips: `data/precomputed_pose/` (ignored).
2. Biomechanics metrics (freestyle, underwater side view first), shown through that flow.
3. Personalized issue detection. 4. Feedback, checkpoints, verified evidence, LLM layer.
5. History and optimization. 6. Training and calendar. 7. Hardening, full scenario tests,
   production inference and deployment evaluation.

One working end-to-end flow comes before breadth of metrics. Do not start a phase without
the owner's approval. After each phase, stop and report.

## Testing and status claims

- Before reporting: `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .`,
  and in `frontend/`: `npm run lint`, `npm run build`. If something could not be run, say why.
  `tests/test_emulator_rules.py` only runs when the emulators are up
  (`npm --prefix frontend run emulators`); say whether it ran or was skipped.
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
