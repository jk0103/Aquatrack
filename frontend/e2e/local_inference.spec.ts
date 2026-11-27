// Real local inference through the web app. Runs only when asked for, against a backend
// started with AQUATRACK_POSE_SOURCE=local (models in models/, see docs/INFERENCE_WORKER.md):
//
//   LOCAL_INFERENCE=1 npx playwright test e2e/local_inference.spec.ts
//
// The clip uploaded here has no saved pose file, so the result can only come from the
// detector and the pose model running on this upload. Slow: the models run on this machine.
import { existsSync } from "node:fs";
import path from "node:path";

import { expect, test } from "@playwright/test";

import { adminOwned, newSwimmer, onboard, REPO, signUp, uid } from "./helpers";

const CLIP = path.join(REPO, "test_videos/derived/front_crawl_mirrored_720p.mp4");
const DOCS = "http://127.0.0.1:8080/v1/projects/demo-aquatrack/databases/(default)/documents";

test.skip(process.env.LOCAL_INFERENCE !== "1" || !existsSync(CLIP), "local inference run not requested");
test.setTimeout(900_000);

test("a clip with no saved pose is analysed by the models and its result and advice are shown", async ({ page }) => {
  const swimmer = newSwimmer();
  await signUp(page, swimmer);
  await onboard(page);
  const owner = await uid(page);
  await page.goto("/analyze");
  await page.locator('input[type="file"]').setInputFiles(CLIP);
  await page.locator("#stroke").selectOption("Freestyle");
  await page.getByRole("button", { name: /Upload|Analyze|Save/ }).last().click();
  const link = page.getByRole("link", { name: /result|analysis|video|View|Open/i }).first();
  await expect(link).toBeVisible({ timeout: 120_000 });
  await link.click();
  await expect(page).toHaveURL(/\/history\/.+/);
  // the job runs on the page: progress first, then the result, without a reload
  await expect(page.getByText(/Analyzing your swim|Waiting to start/).first()).toBeVisible({ timeout: 60_000 });
  await expect(page.getByRole("heading", { name: "Coaching suggestions" })).toBeVisible({ timeout: 800_000 });
  // not saved pose data: the notice for it must be absent
  await expect(page.getByText(/extracted earlier from this\s+exact video/)).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "General practice" })).toBeVisible();
  await page.screenshot({ path: "e2e-results/local-inference-result.png", fullPage: true });

  const video = (await adminOwned("videos", owner))[0];
  const id = video.name.split("/").pop()!;
  const admin = { Authorization: "Bearer owner" };
  const doc = await (await fetch(`${DOCS}/videos/${id}`, { headers: admin })).json();
  const analysisId = doc.fields.latestAnalysisId.stringValue;
  const analysis = await (await fetch(`${DOCS}/videos/${id}/analyses/${analysisId}`, { headers: admin })).json();
  expect(analysis.fields.pose_source.stringValue).toBe("local");
  const adviceId = doc.fields.latestAdviceId.stringValue;
  // opening the page again reads the stored advice: the id does not change
  await page.reload();
  await expect(page.getByRole("heading", { name: "Coaching suggestions" })).toBeVisible({ timeout: 60_000 });
  const again = await (await fetch(`${DOCS}/videos/${id}`, { headers: admin })).json();
  expect(again.fields.latestAdviceId.stringValue).toBe(adviceId);
  const advice = await fetch(`${DOCS}/videos/${id}/advice`, { headers: admin }).then((r) => r.json());
  expect(advice.documents).toHaveLength(1);
});
