# Implementation status (2026-11-16, after Phase 7)

One list of what exists and how far each part has actually been checked. **Passing tests do
not make the application production-ready.** Launch blockers are in section 3.

Status words used below:

1. **Tested** — implemented, automated tests, and exercised in the browser against the emulators
2. **Synthetic only** — implemented, but its logic has only run on labelled synthetic data
3. **Emulator only** — implemented and tested, but never against a real Firebase project
4. **Partial** — some of it is missing
5. **Mock** — placeholder or example content, labelled as such
6. **Blocked: infrastructure** — cannot be completed without infrastructure that is not approved
7. **Blocked: validation** — works as software; what it claims has not been scientifically validated

Everything runs only against the Firebase emulators, so status 3 applies to every row that
touches Firebase; it is not repeated in each line.

## 1. Features

| Area | Feature | Status | Notes |
| --- | --- | --- | --- |
| Accounts | Sign up, log in, log out (Firebase Auth) | 1, 3 | Email and password only. No email verification, password reset screen or MFA |
| Accounts | Account deletion | 1, 3 | Emulator, disposable accounts. Production needs: section 3 |
| Profile | Onboarding survey, profile, goals, target, personal bests | 1, 3 | Self-reported; never analysed beyond level and goals |
| Profile | Training preferences | 1, 3 | |
| Upload | Direct upload to Storage with owner, type and size rules | 1, 3 | Type is the browser's claim; the worker checks the file itself |
| Inference | Pose from saved files (`precomputed`) | 1 | **Development fixture, not inference.** Real model output for 3 public clips |
| Inference | Pose from the models on the worker (`local`) | 4, 6 | Prepared in Phase 8: verified model loading, start-up preflight, container, acceptance test and budget. **Still never run: no real inference in the worker.** Needs the owner's approval of licences, provider and budget |
| Inference | Remote inference service (`remote`) | 5 | A stub that reports "not available" |
| Jobs | Durable queue, leases, recovery, cancel, timeout, limits | 1, 3 | Tested with fake inference adapters and in the Firestore emulator; never under real load or on a second machine |
| Jobs | Standalone worker process (`python -m aquatrack.worker`) | 1 (logic), 6 (deployment) | Same code as the embedded worker; not run as a separate deployed service |
| Analysis | Pose cleaning, quality grade, stroke cycles | 1, 7 | Compared with manual annotation on 2 real clips (`docs/PHASE2_VALIDATION.md`) |
| Analysis | Biomechanics metrics with per-metric reliability | 1, 7 | 11 metrics; freestyle, underwater side view only |
| Analysis | Other strokes, above-water or oblique footage | 4 | Reported as limited or not measurable |
| Interpretation | Observations, issue candidates, priorities | 2, 7 | On real clips: observations only, zero issues. Issue rules and priorities only ran on synthetic data |
| Feedback | Five categories, checkpoints, references | 2 (issues), 1 (observations) | Evidence library: 10 sources, abstracts only |
| Feedback | Rewording by an OpenAI model | 2 (mocked) | Off by default. **No real call has ever been made**; account access and real output unverified |
| History | Upload list, filters, detail page, video deletion | 1, 3 | |
| History | Session comparison, progress series, checkpoint follow-up | 2 | No real swimmer has two comparable sessions; on the real pair the answer is "not comparable" |
| Training | Activity library with checked sources | 1, 7 | 14 activities; nothing tested on swimmers |
| Training | Goal-based single session and 7-day plan | 1, 7 | |
| Training | Analysis-based recommendations | 2 | Only with synthetic findings |
| Training | Edit, reschedule, complete, skip, cancel, regenerate, versions | 1, 3 | Conflict protection added in Phase 7 |
| Calendar | Month and week view of stored sessions | 1, 3 | No reminders, no external calendar |
| Home | Uploads and this week's training | 1 | Time chart and feedback card below are **Mock** (labelled Example) |
| Progress | Measured progress, recorded training | 1 / 2 | Race-time chart at the bottom is **Mock** (labelled Example) |
| Feedback page `/feedback/[id]` | Example feedback | 5 | Entirely example content, labelled; real feedback is on `/history/[id]` |
| Profile | Headline stats | 5 | Example, labelled |
| Security | Ownership in rules and in the API, limits, rate limiting | 1, 3 | Review in `docs/SECURITY_REVIEW.md`; no external penetration test |
| Operations | Environments, config validation, health checks | 1 | No deployment exists |

## 2. What "tested" rests on

| Kind of check | What it shows | What it does not show |
| --- | --- | --- |
| Unit and service tests (pytest, in memory) | Rules are followed, edge cases handled | Anything about real swimmers |
| Emulator tests (security rules, Firestore transactions, Auth) | Ownership, atomic claims, deletion | Behaviour of a real project, quotas, indexes, latency |
| Browser journeys (Playwright, 8 tests) | The main screens work end to end | Rendering on phones, accessibility, load |
| Real-pose regression (3 public clips, saved model output) | The pipeline gives stable numbers on real pose data | That inference works on a new upload |
| Fake inference adapters | Worker orchestration | Model speed, memory, failure modes |
| Mocked OpenAI answers | Validation and fallback | What the real model writes |

## 3. Blockers before the free application can be opened to users

AquaTrack is permanently a free, noncommercial student project (owner's decision,
2026-11-16); there is no commercial launch. "Launch" below means opening the free
application to the public. Being noncommercial removes none of these by itself.

| # | Blocker | Kind |
| --- | --- | --- |
| B1 | The inference worker is prepared but has never run the models. The first run is packaged and waits for five approvals (`docs/PHASE_9B_EXECUTION.md`); the end-to-end stage then needs a Firebase project | Infrastructure, approval |
| B2 | Ultralytics YOLO11: by its publisher's pages a hosted service needs the whole project open-sourced under AGPL-3.0 or a paid licence, free or not. Fitting route for this project: AGPL-3.0, after contributor rights are confirmed and the owner approves. Not done (`docs/MODEL_LICENSING_DECISION.md`) | Licensing, decision |
| B3 | RTMW-x checkpoint: no stated terms; at least six of its fourteen training datasets are non-commercial or research-only. A noncommercial project is within the wording of those restrictions, but the publisher has confirmed nothing; ask before a public release | Licensing, unresolved |
| B4 | No licence file in the repository (none is added without contributor rights confirmed and explicit approval); the hero photo's source is not recorded | Licensing |
| B5 | No production Firebase project, backups, retention policy or deletion of backups and logs | Infrastructure, privacy |
| B6 | No legal review: privacy policy, terms, consent for videos of minors, data processing agreements | Privacy |
| B7 | Account deletion depends on the user's request finishing; no background reconciliation | Privacy |
| B8 | Rate limits are per process; no shared limiter, no abuse monitoring, no App Check | Security |
| B9 | No email verification, password reset flow or MFA | Security |
| B10 | Technique findings, comparison thresholds and training plans are not validated on real swimmers | Validation |
| B11 | OpenAI integration never run against the real API | External service |
| B12 | No monitoring, alerting, error tracking or on-call path | Operations |

B2 and B3, update 2026-11-16: the owner reports permission from Ultralytics and the relevant
RTMW-x parties for this noncommercial student project. The written confirmations have not
been reviewed, so both stay open as "permission reported; scope not verified"
(`docs/MODEL_LICENSING_DECISION.md`, section 0.1). They close, use by use, when the written
scope has been read: private development and cloud GPU inference first, free public
deployment separately.

None of B1 to B7 can be closed by more code on this machine.

## School demonstration (2026-11-16)

Account-restricted demonstration on saved pose data for the approved public video:
implemented; unit-tested; emulator-tested (restricted rules, backend gate); browser-tested
locally (`frontend/e2e/demo.spec.ts`). **Not deployed and not tested in any cloud.** It is
not real inference on a new upload and does not change the status of Phase 9B or of the
licensing blockers. Plan, costs, blockers and approvals: `docs/SCHOOL_DEMO_DEPLOYMENT.md`.
