// Browser end-to-end tests of the critical journeys, against the Firebase emulators.
//
//   npm run e2e          (from frontend/)
//
// Everything runs locally: the Firebase Emulator Suite, the API with its embedded worker,
// and the Next.js dev server. If they are already running they are reused; otherwise they
// are started here. The tests use the Chrome that is installed on this machine, so no
// browser is downloaded. No real Firebase project, no paid service and no real user data is
// involved: every account is created by the test and is disposable.
import { defineConfig } from "@playwright/test";

const emulators = {
  FIREBASE_AUTH_EMULATOR_HOST: "127.0.0.1:9099",
  FIRESTORE_EMULATOR_HOST: "127.0.0.1:8080",
  STORAGE_EMULATOR_HOST: "http://127.0.0.1:9199",
  FIREBASE_PROJECT_ID: "demo-aquatrack",
  AQUATRACK_ENV: "emulator",
  AQUATRACK_POSE_SOURCE: "precomputed", // development fixture: saved pose data, not inference
  AQUATRACK_PRECOMPUTED_POSE_DIR: "data/precomputed_pose",
};

export default defineConfig({
  testDir: "./e2e",
  timeout: 120_000,
  expect: { timeout: 20_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL: "http://localhost:3000",
    channel: "chrome",
    headless: true,
    trace: "retain-on-failure",
    viewport: { width: 1280, height: 900 },
  },
  outputDir: "./e2e-results",
  webServer: [
    {
      command: "npm run emulators",
      url: "http://127.0.0.1:4000",
      reuseExistingServer: true,
      timeout: 180_000,
    },
    {
      command: "uv run uvicorn aquatrack.api.main:app --port 8000",
      cwd: "..",
      env: emulators,
      url: "http://127.0.0.1:8000/health",
      reuseExistingServer: true,
      timeout: 120_000,
    },
    {
      command: "npm run dev",
      env: { NEXT_PUBLIC_FIREBASE_EMULATORS: "true" },
      url: "http://localhost:3000/login",
      reuseExistingServer: true,
      timeout: 180_000,
    },
  ],
});
