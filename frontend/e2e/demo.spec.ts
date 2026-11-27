// Rehearsal of the account-restricted school demonstration, in the local emulators.
//
// Runs only when asked for, against servers started in demo mode:
//   1. npm run emulators -- --restricted                 (restricted security rules)
//   2. uv run python scripts/demo_rehearsal_accounts.py  (from the repository root)
//   3. uv run python scripts/demo_rehearsal_api.py
//   4. NEXT_PUBLIC_FIREBASE_EMULATORS=true NEXT_PUBLIC_AQUATRACK_ACCESS=restricted \
//      NEXT_PUBLIC_AQUATRACK_DEMO=1 npm run dev
//   5. DEMO_REHEARSAL=1 npx playwright test e2e/demo.spec.ts
//
// The pose data is the file the real models produced earlier for the approved public clip;
// no model runs here. This is a local rehearsal: it says nothing about a cloud deployment.
import { existsSync, readFileSync } from "node:fs";
import path from "node:path";

import { expect, test, type Page } from "@playwright/test";

import { adminOwned, idToken, PUBLIC_CLIP, REPO, uid } from "./helpers";

const ACCOUNTS = path.join(REPO, "frontend/.env.demo-rehearsal.local");
const OTHER_CLIP = path.join(REPO, "test_videos/public/sprint_front_crawl_underwater.webm");
const ready =
  process.env.DEMO_REHEARSAL === "1" &&
  existsSync(ACCOUNTS) &&
  existsSync(PUBLIC_CLIP) &&
  existsSync(OTHER_CLIP);

function account(kind: "INVITED" | "STRANGER") {
  const text = readFileSync(ACCOUNTS, "utf8");
  const value = (name: string) => new RegExp(`^${name}=(.*)$`, "m").exec(text)![1];
  return { email: value(`DEMO_${kind}_EMAIL`), password: value(`DEMO_${kind}_PASSWORD`) };
}

async function logIn(page: Page, who: { email: string; password: string }) {
  await page.goto("/login");
  await page.getByLabel("Email").fill(who.email);
  await page.getByLabel("Password", { exact: true }).fill(who.password);
  await page.getByRole("button", { name: "Log in" }).click();
}

async function upload(page: Page, file: string) {
  await page.goto("/analyze");
  await expect(page.getByText(/This is a demonstration environment/)).toBeVisible();
  await expect(page.getByText(/do not run on this\s+site/)).toBeVisible();
  await page.locator('input[type="file"]').setInputFiles(file);
  await page.locator("#stroke").selectOption("Freestyle");
  await page.getByRole("button", { name: /Upload|Analyze|Save/ }).last().click();
  const link = page.getByRole("link", { name: /result|analysis|video|View|Open/i }).first();
  await expect(link).toBeVisible({ timeout: 90_000 });
  await link.click();
  await expect(page).toHaveURL(/\/history\/.+/);
}

test.describe.configure({ mode: "serial" });
test.skip(!ready, "demo rehearsal not requested (DEMO_REHEARSAL=1) or its local files are missing");

test("sign-up is closed and says so", async ({ page }) => {
  await page.goto("/login");
  await expect(page.getByText(/invited accounts only/)).toBeVisible();
  await expect(page.getByRole("link", { name: "Create an account" })).toHaveCount(0);
  await page.goto("/signup");
  await expect(page.getByRole("heading", { name: "Sign-up is closed" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Create account" })).toHaveCount(0);
});

test("an account that was not invited is turned away, by the backend and by the rules", async ({ page }) => {
  await logIn(page, account("STRANGER"));
  await expect(page.getByText(/isn't authorized for this AquaTrack demonstration/)).toBeVisible();
  await expect(page).toHaveURL(/\/login/);
  await page.goto("/analyze");
  await expect(page).toHaveURL(/\/login/); // signed out again

  // The same account with a valid token, straight at the backend and at Firebase:
  // sign in without the app's own check getting in the way.
  const s = account("STRANGER");
  const res = await fetch(
    "http://127.0.0.1:9099/identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key=demo-key",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...s, returnSecureToken: true }),
    },
  );
  const { idToken: token, localId } = await res.json();
  for (const [method, route] of [
    ["GET", "/me"],
    ["GET", "/progress"],
    ["POST", "/videos/anything/analyze"],
    ["GET", "/training/calendar"],
  ]) {
    const api = await fetch(`http://127.0.0.1:8000${route}`, {
      method,
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(api.status, route).toBe(403);
  }
  const docs = "http://127.0.0.1:8080/v1/projects/demo-aquatrack/databases/(default)/documents";
  const own = await fetch(`${docs}/profiles/${localId}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(own.status).toBe(403);
  const put = await fetch(
    `http://127.0.0.1:9199/v0/b/demo-aquatrack.appspot.com/o?name=${encodeURIComponent(`videos/${localId}/x.webm`)}`,
    {
      method: "POST",
      headers: { Authorization: `Firebase ${token}`, "Content-Type": "video/webm" },
      body: "x",
    },
  );
  expect(put.status).toBe(403);
});

test("the invited account uploads the approved video and gets a real analysis and feedback", async ({ page }) => {
  await logIn(page, account("INVITED"));
  await expect(page).toHaveURL(/localhost:\d+\/(onboarding)?$/);
  const owner = await uid(page);
  await upload(page, PUBLIC_CLIP);

  // the job runs: its state is shown first, then the result, without reloading
  await expect(page.getByRole("heading", { name: "No clear technique issue in this clip" })).toBeVisible({ timeout: 110_000 });
  // saved pose data is disclosed without opening anything
  await expect(page.getByText(/extracted earlier from this\s+exact video/)).toBeVisible();
  await page.getByText("Full analysis details").click();
  await expect(page.getByRole("heading", { name: "Improvement priorities" })).toBeVisible();
  await expect(page.getByText("Measured in your video")).toBeVisible();
  await expect(page.getByText(/extracted earlier from this\s+exact video/)).toBeVisible();
  await expect(page.getByText(/not\s+produced by a live model run/)).toBeVisible();
  // what the stored evidence supports for this clip: observations, no invented problem
  await expect(page.getByText(/No priorities from this video/)).toBeVisible();

  // the uploaded video plays, and a supporting timestamp moves the player
  const video = page.locator("video").first();
  await expect(video).toBeVisible();
  await expect.poll(async () => video.evaluate((v: HTMLVideoElement) => v.readyState)).toBeGreaterThan(0);
  const stamp = page.getByRole("button", { name: /\d+(\.\d+)? ?s/ }).first();
  test.info().annotations.push({
    type: "timestamp navigation",
    description: (await stamp.count()) ? "exercised" : "no timestamp button on this result",
  });
  await page.screenshot({ path: "e2e-results/demo-result.png", fullPage: true });
  if (await stamp.count()) {
    await stamp.click();
    await expect.poll(async () => video.evaluate((v: HTMLVideoElement) => v.currentTime)).toBeGreaterThan(0);
  }

  const videos = await adminOwned("videos", owner);
  expect(videos.map((v) => v.fields.status.stringValue)).toContain("ready");
  const analyses = await fetch(
    `http://127.0.0.1:8000/progress`,
    { headers: { Authorization: `Bearer ${await idToken(page)}` } },
  );
  expect(analyses.status).toBe(200);
});

test("another video is refused with a plain explanation and no result", async ({ page }) => {
  await logIn(page, account("INVITED"));
  await expect(page).toHaveURL(/localhost:\d+\/(onboarding)?$/);
  await upload(page, OTHER_CLIP);
  await expect(page.getByText("The analysis couldn't finish.")).toBeVisible({ timeout: 110_000 });
  await expect(page.getByText(/can't be analysed in the demonstration environment/)).toBeVisible();
  await expect(page.getByText(/never used in its place/)).toBeVisible();
  await expect(page.getByRole("button", { name: "Try again" })).toHaveCount(0);
  await expect(page.getByText("Measured in your video")).toHaveCount(0);
});

test("the demonstration data can be deleted afterwards", async ({ page }) => {
  await logIn(page, account("INVITED"));
  await expect(page).toHaveURL(/localhost:\d+\/(onboarding)?$/);
  const owner = await uid(page);
  const token = await idToken(page);
  for (const v of await adminOwned("videos", owner)) {
    const id = v.name.split("/").pop()!;
    const res = await fetch(`http://127.0.0.1:8000/videos/${id}`, {
      method: "DELETE",
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(res.status).toBeLessThan(300);
  }
  expect(await adminOwned("videos", owner)).toHaveLength(0);
});
