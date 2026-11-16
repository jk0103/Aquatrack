# Security and privacy review (2026-11-16)

An internal review of the code and rules as they are, against the Firebase emulators. It is
not a penetration test and not a legal review. "Fixed" means changed in Phase 7.

## 1. Findings

| Area | State | Detail |
| --- | --- | --- |
| Authentication | OK for development | Firebase Auth ID tokens verified by the Admin SDK on every API route; every route but `/health` and `/health/ready` needs a login. **Open:** no email verification, no password reset screen, no MFA, no session revocation check (`check_revoked` is off, so a token stays valid up to an hour after sign-out or deletion) |
| API authorization | OK | Every route takes the uid from the verified token, never from the request. Someone else's video or session answers exactly like a missing one (404) |
| Cross-user access | OK | Tested per route (API), per collection (rules) and in the browser |
| Firestore rules | OK | Clients can create only their own profile and upload record. Job state, analyses, interpretations, feedback, training plans and sessions are backend-write only. **Fixed:** profile delete denied; no writes while an account is being deleted; bookkeeping collections invisible |
| Storage rules | OK | Own folder only, `video/*`, under 500 MB, no overwrite, no client delete. Analysis artifacts owner-read, backend-write |
| Upload validation | **Fixed** | The content type and size on the upload record come from the browser. The worker now checks the file itself: real size, decodable as video, duration (2 to 180 s), frame count, resolution (up to 4096 px). A non-video file is refused before any inference |
| Malformed media | Partly | Decoding uses OpenCV/FFmpeg inside the worker. A crafted file that crashes the decoder kills the worker; the job is then recovered twice and failed (`worker_interrupted`). **Open:** the worker is not sandboxed beyond its container |
| Resource exhaustion | **Fixed**, partly | Per-swimmer cap of 2 active jobs, job timeout, length and resolution limits, request rate limits. **Open:** limits are per process (not shared between API instances); no global queue cap; no App Check |
| Rate limiting | **Fixed**, partly | In-memory, per swimmer and kind of request (analyse 20/h, plans 60/h, writes 240/min, reads 600/min, account deletion 5/h), answering 429 with `Retry-After`. Unauthenticated routes are not limited (only the health checks) |
| Duplicate uploads | Recorded | The file's SHA-256 is stored on the video when analysed. The same file uploaded twice is analysed twice; nothing breaks, cost is bounded by the caps |
| OpenAI key | OK | Read by the SDK from the backend environment only; never in the frontend bundle, never in a response (tested), never logged (tested). A key alone does not enable calls |
| Error messages | OK | Job errors are fixed sentences with stable codes; no paths, bucket names or stack traces (tested). `/health/ready` reports counts only |
| Logging | OK, with a note | Logs carry video ids and error class names, never tokens, emails, file contents or notes. Video ids are opaque but are identifiers: log retention must follow the retention policy |
| Download URLs | Note | The web app plays a video through a Firebase download URL. Such a URL carries a long-lived token and keeps working until the object is deleted or the token revoked; it is only ever handed to the signed-in owner. **Open:** short-lived signed URLs would be safer for production |
| Untrusted metadata | OK | Stroke, camera, distance and file name are stored as typed; they select wording and comparability and never reach a shell, a path or a model. File names are never sent to the language model |
| Analysis output access | OK | Owner-read rules; API reads check `uid` on every stored document |
| Training access | OK | Owner-read rules, backend-only writes, validated edits. **Fixed:** concurrent edits cannot overwrite each other |
| Deletion | **Improved** | Video deletion (Phase 5) plus account deletion. See `docs/DATA_LIFECYCLE.md` |
| Prompt injection | Low exposure | Nothing a swimmer types reaches the model: payloads are built from the engine's own text. The model's answer is validated and discarded on any violation |
| CORS / CSRF | Note | The browser calls the API through the Next.js `/api` proxy with a bearer token, not cookies, so CSRF does not apply. Production must restrict the API to that origin |
| Dependencies | Note | `npm audit` reports findings in the frontend tree; not triaged. No automated dependency review yet. Python 3.11 support in Google's client libraries ends in October 2027 |
| Secrets in the repository | OK | No keys, tokens or credentials in tracked files (checked before each commit). `.env` is ignored |

## 2. Open items before real users

1. Email verification, password reset, optional MFA; `check_revoked` on sensitive routes.
2. A shared rate limiter and Firebase App Check; a global queue cap.
3. Short-lived signed URLs for video playback.
4. The worker in a locked-down container with no outbound access except Firebase.
5. CORS restricted to the deployed frontend origin; security headers on the frontend.
6. Dependency scanning in CI and a triage of current `npm audit` findings.
7. An external security test.
8. Review of what must stay out of the public repository: `docs/RELEASE_PLAN.md`.
