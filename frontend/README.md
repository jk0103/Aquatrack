# Aquatrack web app

Next.js (App Router, TypeScript, Tailwind) front end. Accounts, swimmer profiles and videos
live in Firebase:

- **Authentication** (email and password) for sign up and log in
- **Firestore**: `profiles/{uid}` holds the signup survey answers, `videos/{id}` one record per upload
- **Storage**: video files at `videos/{uid}/{id}.{ext}`

Security rules are in `../firebase/`. Calls to the FastAPI backend go through `/api/*`, which
`next.config.ts` forwards to `API_URL` (default `http://localhost:8000`), with the user's
Firebase ID token attached (`app/lib/api.ts`).

## Connect your Firebase project

1. In the [Firebase console](https://console.firebase.google.com), create a project and enable
   **Authentication > Email/Password**, **Firestore Database** and **Storage** (Storage needs the
   pay-as-you-go Blaze plan).
2. Under **Project settings > Your apps**, register a web app and copy its config into
   `frontend/.env.local` (start from `.env.local.example`).
3. Publish the security rules: paste `../firebase/firestore.rules` into Firestore > Rules and
   `../firebase/storage.rules` into Storage > Rules, or run
   `npx firebase deploy --only firestore:rules,storage --project <your-project-id> --config ../firebase.json`.
4. For the backend, set `FIREBASE_PROJECT_ID` (and later `GOOGLE_APPLICATION_CREDENTIALS`) in
   the repo's `.env`.

## Run locally

From the repo root:

```bash
uv run uvicorn aquatrack.api.main:app --reload --env-file .env
```

In another terminal:

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:3000. You'll be sent to the login page; create an account from there.

### Without a Firebase project

`npm run emulators` starts local Auth, Firestore and Storage emulators (needs Java 21+; the
script picks a suitable installed JDK by itself) with an
admin UI at http://localhost:4000. Set `NEXT_PUBLIC_FIREBASE_EMULATORS=true` in `.env.local`
and `FIREBASE_AUTH_EMULATOR_HOST=127.0.0.1:9099` in the repo's `.env`. Emulator data is wiped
when they stop.

## Pages

- `/signup`, `/login`: account pages (`app/(auth)/`)
- `/onboarding`: profile survey shown right after sign up
- `/`, `/analyze`, `/training`, `/calendar`, `/progress`, `/history`, `/profile`: the app
  (`app/(app)/`), which sends logged-out visitors to `/login`
- `/history/[id]`: one of the swimmer's own uploads: the real video from Storage, the session
  details and where analysis stands
- `/feedback/[id]`: example analyses only (ids from `app/lib/mock.ts`)

### Real data vs. examples

| Page | Real (Firebase) | Example (`app/lib/mock.ts`, labelled on the page) |
| --- | --- | --- |
| Home | Upload count, latest three uploads, greeting and date | Week strip, training plans, 100 m chart, coming up, example feedback |
| Analyze | Everything: uploads to Storage, record in Firestore | — |
| History | Uploads list and `/history/[id]`, including real analysis status and results | "Example analyses" list |
| Feedback | — (real results show on `/history/[id]`) | All of it |
| Profile | Survey answers and personal bests | Headline stats |
| Training, Calendar, Progress | — | All of it |

### Video records

`videos/{id}` in Firestore holds `uid`, `storagePath`, `fileName`, `sizeBytes`, `contentType`,
`status`, `createdAt`, `stroke`, `camera` (filming angle), `distance`, `comments` (session
notes), `wantFeedback` and `wantPlan`. Newer uploads may also have `poolLength`,
`timeSeconds`, `sessionDate` (`YYYY-MM-DD`) and `durationSeconds`. These are optional, and
records without them still load (`toRecord` in `app/lib/videos.ts`). The security rules allow
these extra fields as they are, so no rules change was needed.

### Analysis (v1)

After an upload the app calls `POST /api/videos/{id}/analyze`. The backend sets the video's
`status` (`uploaded`, `queued`, `analyzing`, `ready`, `failed`) and a `job` field with the
attempt count and, on failure, a message for the swimmer. `/history/[id]` listens to the
video record (`watchVideo`), so status changes appear without a reload, and offers a retry
when the failure is retryable.

Results are one document per run at `videos/{id}/analyses/{analysisId}` (read-only for the
owner, written only by the backend). `app/lib/analysisV1.ts` parses them and
`app/components/AnalysisPanel.tsx` shows, for schema 1.1 results, what the analysis can stand
behind (tracking, arms seen, stroke cycles, measurements), then each metric with its own status,
spread, evidence, limits and buttons that jump to the moment in the video, and the list of what
is not measured, with reasons. Results from schema 1.0 keep their original layout. Nothing on
that panel is example data, and nothing on it judges the technique.
The contract is defined in `src/aquatrack/contracts.py`.

### Not in the product scope yet

The project overview centres on technique feedback, performance history and next-video
checkpoints. Training plans, the training calendar and "Add event" / "Mark session done"
are generic training-management features with no backend. They are kept as labelled
examples and their buttons are disabled ("soon") rather than removed. Whether to build them
out or drop them is still to be decided.

## Checks

```bash
npm run lint
npm test        # parser tests for analysis results (Node's built-in runner)
npm run build
```
