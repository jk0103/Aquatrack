# Aquatrack web app

Next.js (App Router, TypeScript, Tailwind) front end. It talks to the FastAPI backend through
`/api/*`, which `next.config.ts` forwards to `API_URL` (default `http://localhost:8000`).

## Run locally

In one terminal, from the repo root:

```bash
uv run uvicorn aquatrack.api.main:app --reload
```

In another:

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:3000. You'll be sent to the login page; create an account from there.

## Pages

- `/signup` and `/login`: account pages (`app/(auth)/`)
- `/`: home, only for logged-in users (`proxy.ts` redirects everyone else to `/login`)

## Checks

```bash
npm run lint
npm run build
```
