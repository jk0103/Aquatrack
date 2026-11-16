# GitHub and release preparation (plan only; nothing has been pushed)

AquaTrack is permanently a free, noncommercial student project (owner's decision,
2026-11-16). "Release" here means publishing the source and, separately, opening a free
application to users. There is no commercial release.

## 1. Where things are

- `main` and `origin/main`: `4ce80ca`, unchanged.
- `feature/aquatrack-completion`: 41 commits ahead of `main` after the Phase 6 commit (the
  student's earlier commits, three early commits authored as "Claude", merges of three
  feature branches, and one commit per phase 1 to 6). Phase 7 is uncommitted.
- Phase commits: `6aa3852` (1), `1357fba` (2), `c0e482e` (3), `4e46baa` (4), `5beb945` (5),
  `1a9e02c` (6). All use the repository's configured identity (the student's, recorded as
  authorised in `CLAUDE.md`) with a `Co-Authored-By` line. **If the owner wants a different
  author, that has to be decided before pushing**: changing it afterwards means rewriting
  history, which is not allowed here.
- Remote research branches (`origin/claude/*`, `origin/feature/web-ui-improvements`) are
  untouched and stay.

## 2. What may be pushed, and what must stay private

| Content | Push? |
| --- | --- |
| `src/`, `tests/`, `frontend/` source, `firebase/` rules, `docs/*.md`, `scripts/`, CI | yes |
| `experiments/` (detector comparison, validation sheets, evidence lookups) | no: untracked, may hold Drive identifiers and frames from videos |
| `data/` (pose dumps), `test_videos/`, `models/`, any `*.pt`, `*.onnx`, video files | no: ignored |
| The Project Overview PDF in `docs/` | no: private, personal information |
| `.env`, `frontend/.env.test.local`, any key | no: ignored |
| Colab notebooks | no (they stay with the student) |
| `frontend/e2e-results/`, emulator logs | no: ignored |

Before any push: `git status --short --ignored`, `git ls-files | grep -Ei
'\.(ipynb|pdf|mp4|mov|webm|npz|onnx|pt)$'` (must be empty), a search of the diff for Drive
links, emails and keys, and a look at `git log --stat main..HEAD` for anything large.
Currently tracked media: only `frontend/public/images/hero-butterfly.jpg` (see section 4).

## 3. Push and pull request (after approval)

1. Push `feature/aquatrack-completion` as a new remote branch. No force, no rebase.
2. Open a pull request into `main`; do not merge it in the same step. Description: phases 1
   to 7, what is validated and what is not (`docs/IMPLEMENTATION_STATUS.md`).
3. CI must pass. Review by the owner.
4. Merge with a merge commit (keeps the student's history). No squash.

Branch protection for `main` (recommended): pull requests only, CI required, no force push,
no deletion, at least one review.

## 4. Licences

The full review of the two models, the strategies and the open questions is in
`docs/MODEL_LICENSING_DECISION.md`; the table below is the summary.

| Component | Licence | Consequence |
| --- | --- | --- |
| Ultralytics YOLO11 (`ultralytics`, `yolo11m.pt`) | AGPL-3.0, or a paid licence (ultralytics.com/license; the repository's licence file) | **Blocker for any hosted use, free or not.** By Ultralytics' pages the test is open source or not. For this free student project the fitting route is publishing the whole project under AGPL-3.0; a paid licence is not an objective. Pretrained weights fall under the same licence |
| MMPose / RTMW code, rtmlib | Apache-2.0 | fine; keep notices |
| RTMW-x pretrained weights | no stated terms; trained on 14 datasets, at least six of them research-only or noncommercial | **Unconfirmed even for free use.** A noncommercial project is within the wording of the restrictions found; the publisher has said nothing about the checkpoint. Ask before a public release |
| ONNX Runtime | MIT | fine. CUDA and cuDNN in a GPU image have NVIDIA's own terms (not checked) |
| FastAPI, Pydantic, NumPy, OpenCV, Firebase SDKs, Next.js, React, Tailwind, Playwright, OpenAI SDK | permissive (MIT, BSD, Apache-2.0) | fine; an automated licence report should confirm the whole tree |
| This repository | **no LICENSE file** | AGPL-3.0 is the fitting choice if YOLO11 stays. Not to be added until contributor rights are confirmed and the owner explicitly approves (`docs/MODEL_LICENSING_DECISION.md`, section 4) |
| `frontend/public/images/hero-butterfly.jpg` | source and licence not recorded in the repository | find the source or replace the image before publishing |
| Public test clips | sources and licences are in the local, untracked `test_videos/public/SOURCES.md`; the clips are not in the repository | keep them out, or add only with their attribution |
| Evidence and training sources | cited, not copied | fine |

This table is an engineering reading of published licence texts, not legal advice.

## 5. CI

`.github/workflows/ci.yml` runs on pull requests: `ruff check`, `ruff format --check`,
`pytest` (emulator tests skip themselves), and for the frontend lint, type check, unit tests
and build. To add later: the emulator tests and the browser journeys (needs Java 21 for the
emulators and Chrome on the runner; the journeys that need the public clip skip without it),
a dependency audit (`npm audit`, `pip-audit`), a licence report, and secret scanning.

## 6. Versions and release gates

- Version the app as `0.x` until launch blockers are closed; tag a release only from `main`.
- Stored-data versions are already separate and recorded with every document: analysis 1.2,
  interpretation 1.0, rules 2026.11-2, evidence 2026.11-1, feedback 1.0, comparison 1.0,
  training 1.0, activity library 2026.11-1.
- Gates, each needing the owner's explicit approval: (1) push, (2) merge to `main`,
  (3) staging deployment, (4) first real inference run, (5) any cost at all (infrastructure
  only: no commercial licence is planned), (6) production Firebase, (7) adding a licence file
  or making the repository public, (8) opening the free application to the public, which
  additionally needs every blocker in
  `docs/IMPLEMENTATION_STATUS.md` section 3 closed or consciously accepted.
