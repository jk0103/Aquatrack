# Data lifecycle, deletion and retention

What AquaTrack stores for an account, how it is deleted, and what a real deployment still
has to decide. **This is engineering documentation, not a statement of legal compliance.**
No legal review has been done.

## 1. What an account owns

| Data | Where | Written by | Deleted by |
| --- | --- | --- | --- |
| Sign-in (email, password hash, display name) | Firebase Auth | the user | account deletion |
| Profile, goals, target, personal bests, note, training preferences | `profiles/{uid}` | the user (rules) | account deletion |
| Uploaded videos | Storage `videos/{uid}/` | the user (rules) | video or account deletion |
| Upload record, job state | `videos/{id}` | user creates; backend updates | video or account deletion |
| Pose arrays (raw and cleaned) | Storage `analysis/{uid}/{id}/` | backend | video or account deletion |
| Analyses, interpretations, feedback | `videos/{id}/…` | backend | video or account deletion |
| Comparisons, progress | not stored (computed on request) | — | — |
| Training plans and sessions, notes, completion | `training_plans`, `training_sessions` | backend | session delete, account deletion |
| Schedule revision counter | `training_state/{uid}` | backend | account deletion |
| Deletion marker | `account_deletions/{uid}` | backend | removed when deletion finishes |

Sent outside Firebase: nothing by default. With OpenAI rewording switched on, structured
feedback and plan text (no identifiers, no notes, no video) is sent to OpenAI; see section 4.

## 2. Deleting a video

`DELETE /videos/{id}` — `docs/HISTORY_AND_DELETION.md`. Pointers from training data are
cleared first; training history stays.

## 3. Deleting an account

`DELETE /me` with `{"confirm": "DELETE MY ACCOUNT"}`; in the app: Profile, "Delete my account",
type the phrase.

1. A marker `account_deletions/{uid}` is written. From then on the API refuses to start
   analyses, save plans or change sessions for the account, and the security rules refuse new
   upload records and profile writes.
2. Every video is deleted with the video-deletion procedure (a running analysis stops and
   stores nothing).
3. Training sessions, plans and the schedule counter are deleted.
4. The profile is deleted.
5. The sign-in is deleted in Firebase Auth.
6. The marker is deleted.

If a step fails the answer is 503 without internals, the marker stays, and the same request
finishes the job. Repeating a finished deletion is harmless.

Checked: unit tests with a failure injected at each step; an emulator test with a real Auth
emulator account, Storage files and Firestore documents; a browser test through the Profile
page. All with disposable accounts.

**Not production-ready**, because:

- If the user never retries after a failure, nothing finishes the deletion. A real service
  needs a background job that completes every marker older than a few minutes.
- If step 5 succeeds and step 6 fails, a marker with only the uid and a date is left behind.
- An ID token issued before deletion still verifies for up to an hour (it finds no data).
- Backups, exports and logs are outside this procedure.

## 4. Retention checklist for a real deployment

| Item | Decision needed | Current state |
| --- | --- | --- |
| Uploaded videos | keep until the user deletes, or a maximum age | kept until deleted |
| Raw pose arrays | needed only to re-run analysis; consider deleting after N days | kept until deleted |
| Failed or abandoned uploads | automatic clean-up after N days | kept |
| Inactive accounts | notify and delete after N months | not handled |
| Firestore and Storage backups | whether they exist, how long, and how deletions reach them | no backups configured |
| Application and platform logs | retention period; they hold video ids and uids | not configured |
| Deletion audit record | what may be kept as proof of deletion without keeping personal data | nothing kept |
| OpenAI (if enabled) | `store=false` is set; abuse-monitoring logs are kept by OpenAI for up to 30 days unless Zero Data Retention is approved | off |
| Inference host | whether videos or frames persist on the worker's disk | temp directory, removed after each job |
| Minors | age gate or parental consent; videos of children | not handled |
| Data export | a way for the user to download their data | not built |
| Data processing agreements | Google (Firebase), the hosting provider, the inference host, OpenAI | none in place |
| Region | where data is stored and processed | not chosen |
| Breach response | who is told, how fast | not defined |

## 5. Rollback and backups

There is no production data. Before there is: enable Firestore point-in-time recovery or
scheduled exports and Storage object versioning or soft delete; write down how a deletion
request is re-applied after a restore (restore must not resurrect deleted accounts); test one
restore before launch.
