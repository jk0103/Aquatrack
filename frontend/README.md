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

`npm run emulators` starts local Auth, Firestore and Storage emulators (needs Java) with an
admin UI at http://localhost:4000. Set `NEXT_PUBLIC_FIREBASE_EMULATORS=true` in `.env.local`
and `FIREBASE_AUTH_EMULATOR_HOST=127.0.0.1:9099` in the repo's `.env`. Emulator data is wiped
when they stop.

## Pages

- `/signup`, `/login`: account pages (`app/(auth)/`)
- `/onboarding`: profile survey shown right after sign up
- `/`, `/analyze`, `/training`, `/calendar`, `/progress`, `/history`, `/profile`: the app
  (`app/(app)/`), which sends logged-out visitors to `/login`

Training, calendar, progress and example feedback still use placeholder data from
`app/lib/mock.ts`.

## Checks

```bash
npm run lint
npm run build
```
