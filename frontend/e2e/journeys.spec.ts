// Critical user journeys in a real browser, against the Firebase emulators.
// A: new swimmer   B: video analysis   C: training   D: history   E: privacy
//
// What these are, and are not:
// - Journey B uses a public test clip whose pose data was produced earlier by the real
//   models and is looked up from a local folder: a DEVELOPMENT FIXTURE. It shows the
//   upload-to-feedback path works; it is not model inference on a new video.
// - Journey D uses labelled SYNTHETIC sessions. They test the screens, not anyone's progress.
// - Every account is created here and deleted or left in the disposable emulator.
import { expect, test, type Page } from "@playwright/test";

import {
  adminExists,
  adminOwned,
  HAS_FIXTURE,
  idToken,
  localIso,
  newSwimmer,
  onboard,
  PUBLIC_CLIP,
  seedSyntheticSessions,
  signIn,
  signUp,
  uid,
} from "./helpers";

test.describe.configure({ mode: "serial" });

const swimmer = newSwimmer();
let page: Page;
let owner = "";

test.beforeAll(async ({ browser }) => {
  page = await browser.newPage();
});
test.afterAll(async () => {
  await page.close();
});

test("A. a new swimmer signs up, completes the survey and reaches an honest empty dashboard", async () => {
  await signUp(page, swimmer);
  await onboard(page);
  owner = await uid(page);
  await expect(page.getByRole("heading", { name: /Welcome back, Test/ })).toBeVisible();
  await expect(page.getByText("No swims yet.")).toBeVisible();
  await expect(page.getByText("No sessions planned.")).toBeVisible();
  // example content is still labelled as example
  await expect(page.getByText("Everything below is example data")).toBeVisible();

  await page.goto("/training");
  await expect(page.getByText("Stroke consistency (main)")).toBeVisible();
  await expect(page.getByText(/No analysed video yet/)).toBeVisible();
  await expect(page.getByText("No saved plans yet.")).toBeVisible();
  await expect(page.getByText("Nothing recorded yet.")).toBeVisible();

  // preferences are saved and are still there after a browser refresh
  await page.getByRole("button", { name: "Edit preferences" }).click();
  for (const day of ["Mon", "Wed", "Sat"]) await page.getByText(day, { exact: true }).click();
  await page.getByLabel("Preferred difficulty").selectOption("moderate");
  await page.getByRole("button", { name: "Save preferences" }).click();
  await expect(page.getByText("Mon, Wed, Sat")).toBeVisible();
  await page.reload();
  await expect(page.getByText("Mon, Wed, Sat")).toBeVisible();

  await page.goto("/history");
  await expect(page.getByText(/No (swims|uploads|videos)/i).first()).toBeVisible();
  await page.goto("/progress");
  await expect(page.getByText("Training you recorded")).toBeVisible();
});

test("A. a wrong password is refused and a signed-out visitor cannot open the app", async ({ browser }) => {
  const other = await browser.newPage();
  await other.goto("/training");
  await expect(other).toHaveURL(/\/login/);
  await other.getByLabel("Email").fill(swimmer.email);
  await other.getByLabel("Password", { exact: true }).fill("not-the-password");
  await other.getByRole("button", { name: "Log in" }).click();
  await expect(other.getByRole("alert")).toBeVisible();
  await expect(other).toHaveURL(/\/login/);
  await other.close();
});

test("C. a goal-based plan is previewed, saved, edited, moved, completed and shown everywhere", async () => {
  await page.goto("/training");
  const monday = (() => {
    const d = new Date();
    d.setDate(d.getDate() + ((8 - d.getDay()) % 7 || 7)); // next Monday: always in the future
    return localIso(d);
  })();
  await page.getByLabel("Start date").fill(monday);
  await page.getByRole("button", { name: "Plan 7 days" }).click();
  const preview = page.locator("[aria-live=polite]").filter({ hasText: "Preview, not saved yet" });
  await expect(preview).toBeVisible();
  await expect(preview.getByText("Goal-based").first()).toBeVisible();
  await expect(preview.getByText(/not on a detected technique problem/)).toBeVisible();
  await expect(preview.getByText("Technique practice").first()).toBeVisible();
  expect(await adminOwned("training_plans", owner)).toHaveLength(0); // a preview stores nothing

  await preview.getByRole("button", { name: "Save to my calendar" }).click();
  await expect(page.getByText("Saved 3 sessions to your calendar.")).toBeVisible();
  expect(await adminOwned("training_sessions", owner)).toHaveLength(3);

  // Calendar: the stored sessions are on their days
  await page.goto(`/calendar?date=${monday}`);
  const day = (iso: string) =>
    page.getByRole("button", {
      name: new RegExp(
        new Date(`${iso}T12:00:00`).toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric" }),
      ),
    });
  await expect(day(monday)).toHaveAccessibleName(/1 session/);
  const card = page.getByRole("article").first();
  await expect(card.getByText("Planned", { exact: true })).toBeVisible();

  // Edit: change an activity, add an own one, move it to Tuesday
  const tuesday = localIso(new Date(new Date(`${monday}T12:00:00`).getTime() + 86400000));
  await card.getByRole("button", { name: "Edit or reschedule" }).click();
  await card.getByLabel("Date").fill(tuesday);
  await card.getByLabel(/Minutes for Count your strokes/).fill("5");
  await card.getByLabel("Add your own activity").fill("Backstroke for fun");
  await card.getByRole("button", { name: "Add", exact: true }).nth(1).click();
  await card.getByRole("button", { name: "Save changes" }).click();
  await expect(day(tuesday)).toHaveAccessibleName(/1 session/);
  await expect(day(monday)).not.toHaveAccessibleName(/session/);
  await day(tuesday).click();
  const moved = page.getByRole("article").first();
  await expect(moved.getByText("Edited by you")).toBeVisible();
  await expect(moved.getByText("Changed by you")).toBeVisible();
  await expect(moved.getByText("Added by you")).toBeVisible();
  await expect(moved.getByText(/Moved by you from/)).toBeVisible();

  // Complete it: only when the swimmer says so
  await moved.getByRole("button", { name: "Mark completed" }).click();
  await moved.getByLabel(/Note/).fill("SYNTHETIC e2e note");
  await moved.getByRole("button", { name: "Save as completed" }).click();
  await expect(moved.getByText("Completed", { exact: true })).toBeVisible();
  await expect(moved.getByText("Your note: SYNTHETIC e2e note")).toBeVisible();

  // Still there after the page is loaded afresh
  await page.goto(`/calendar?date=${tuesday}`);
  await expect(page.getByRole("article").first().getByText("Completed", { exact: true })).toBeVisible();

  // Regenerating does not put a second session back on Monday
  await page.goto("/training");
  await page.getByLabel("Start date").fill(monday);
  await page.getByRole("button", { name: "Plan 7 days" }).click();
  await page.getByRole("button", { name: "Save to my calendar" }).click();
  await expect(page.getByText("These dates already have a plan.")).toBeVisible();
  await page.getByRole("button", { name: "Replace, keep my edited sessions" }).click();
  await expect(page.getByText(/Saved \d sessions? to your calendar/)).toBeVisible();
  const live = (await adminOwned("training_sessions", owner)).filter(
    (d) => d.fields.status.stringValue !== "replaced",
  );
  expect(live.map((d) => d.fields.date.stringValue).sort()).toHaveLength(3);
  expect(live.map((d) => d.fields.date.stringValue)).not.toContain(monday);

  // Progress and Training show the recorded practice, apart from measurements
  await expect(page.getByText(/1 completed and 0 skipped in total/)).toBeVisible();
  await page.goto("/progress");
  await expect(page.getByText("Completed in total")).toBeVisible();
  await expect(page.getByText(/not a technique measurement/)).toBeVisible();
});

test("C. an edit from a stale tab is refused instead of overwriting", async ({ browser }) => {
  const sessions = (await adminOwned("training_sessions", owner)).filter(
    (d) => d.fields.status.stringValue === "planned",
  );
  const target = sessions[0];
  const id = target.name.split("/").pop()!;
  const date = target.fields.date.stringValue!;
  await page.goto(`/calendar?date=${date}`);
  const first = page.getByRole("article").first();
  await expect(first.getByRole("button", { name: "Skip" })).toBeVisible();

  // "another device" changes the same session through the API
  const token = await idToken(page);
  const headers = { Authorization: `Bearer ${token}`, "Content-Type": "application/json" };
  const elsewhere = await fetch(`http://127.0.0.1:8000/training/sessions/${id}`, {
    method: "PATCH",
    headers,
    body: JSON.stringify({ revision: 1, time: "05:45" }),
  });
  expect(elsewhere.status).toBe(200);

  await first.getByRole("button", { name: "Skip" }).click(); // this tab still has revision 1
  await expect(page.getByText(/changed somewhere else/)).toBeVisible();
  await expect(page.getByText("05:45").first()).toBeVisible(); // reloaded to what is stored
  const stored = (await adminOwned("training_sessions", owner)).find((d) => d.name.endsWith(id))!;
  expect(stored.fields.status.stringValue).toBe("planned");
  void browser;
});

test("B. a video is uploaded, analysed by the worker and its feedback shown (development fixture)", async () => {
  test.skip(!HAS_FIXTURE, "the local public test clip or its saved pose data is not on this machine");
  await page.goto("/analyze");
  await page.locator('input[type="file"]').setInputFiles(PUBLIC_CLIP);
  await page.locator("#stroke").selectOption("Freestyle");
  await page.getByRole("button", { name: /Upload|Analyze|Save/ }).last().click();
  await expect(page.getByRole("link", { name: /result|analysis|video|View|Open/i }).first()).toBeVisible({ timeout: 90_000 });
  await page.getByRole("link", { name: /result|analysis|video|View|Open/i }).first().click();
  await expect(page).toHaveURL(/\/history\/.+/);
  // processing state first, then the result, without reloading
  await expect(page.getByRole("heading", { name: "No clear technique issue in this clip" })).toBeVisible({ timeout: 110_000 });
  // saved pose data is disclosed without opening anything
  await expect(page.getByText(/extracted earlier from this\s+exact video/)).toBeVisible();
  // AI advice is off in these journeys: the page says so plainly and still gives practice
  await expect(page.getByText(/AI coaching suggestions weren.t made for this video/)).toBeVisible();
  await expect(page.getByRole("heading", { name: "General practice" })).toBeVisible();
  await page.getByText("Full analysis details").click();
  await expect(page.getByRole("heading", { name: "Improvement priorities" })).toBeVisible();
  await expect(page.getByText("Measured in your video")).toBeVisible();
  await expect(page.getByText(/No priorities from this video/)).toBeVisible();
  await expect(page.getByText(/This video gives no reason to correct anything/)).toBeVisible();
  // a supporting timestamp moves the player
  const stamp = page.getByRole("button", { name: /\d+(\.\d+)? ?s/ }).first();
  if (await stamp.count()) {
    await stamp.click();
    await expect.poll(async () => page.locator("video").evaluate((v: HTMLVideoElement) => v.currentTime)).toBeGreaterThan(0);
  }
  await page.reload();
  await expect(page.getByRole("heading", { name: "No clear technique issue in this clip" })).toBeVisible();
  await page.getByText("Full analysis details").click();
  await expect(page.getByText("Measured in your video")).toBeVisible();
  const videos = await adminOwned("videos", owner);
  expect(videos.map((v) => v.fields.status.stringValue)).toContain("ready");
});

test("D. history lists sessions; a compatible pair is compared neutrally and a different effort is not", async () => {
  const [a, b, sprint] = seedSyntheticSessions(owner);
  await page.goto("/history");
  await expect(page.getByText("SYNTHETIC test session 1.mp4")).toBeVisible();
  await page.goto(`/compare?a=${a}&b=${b}`);
  await expect(page.getByText(/increased/i).first()).toBeVisible();
  await expect(page.getByText(/no clearly measurable change/i).first()).toBeVisible();
  // a change is never called progress; the only mention of "better" is the note saying so
  await expect(page.getByText(/improv|worse|got better|is better now/i)).toHaveCount(0);
  await expect(page.getByText(/They don.t say whether it is better/)).toBeVisible();
  await page.goto(`/compare?a=${a}&b=${sprint}`);
  await expect(page.getByText(/different effort/i).first()).toBeVisible();
  await expect(page.getByText(/These two swims cannot be compared/)).toBeVisible();
  await expect(page.getByText(/^(Increased|Decreased)$/)).toHaveCount(0); // nothing is put side by side
  // checkpoint follow-up from the previous video, on the later one
  await page.goto(`/history/${b}`);
  await page.getByText("Full analysis details").click();
  await expect(page.getByText("Checkpoints from your previous video")).toBeVisible();
  await page.goto("/progress");
  await expect(page.getByText(/What each analysis found/)).toBeVisible();
  // someone else's ids give nothing away
  await page.goto("/compare?a=not-mine&b=also-not-mine");
  await expect(page.getByText(/not found|couldn.t/i).first()).toBeVisible();
});

test("E. deleting a video removes everything stored for it and it can no longer be opened", async () => {
  const mine = await adminOwned("videos", owner);
  const victim = mine.find((v) => v.fields.fileName?.stringValue === "SYNTHETIC test session 8.mp4")!;
  const id = victim.name.split("/").pop()!;
  await page.goto(`/history/${id}`);
  await page.getByRole("button", { name: "Delete video…" }).click();
  await page.getByRole("button", { name: "Keep it" }).click(); // cancelling keeps it
  expect(await adminExists(`videos/${id}`)).toBe(true);
  await page.getByRole("button", { name: "Delete video…" }).click();
  await page.getByRole("button", { name: "Yes, delete it permanently" }).click();
  await expect(page).toHaveURL(/\/history$/);
  expect(await adminExists(`videos/${id}`)).toBe(false);
  expect(await adminExists(`videos/${id}/analyses/a1`)).toBe(false);
  await page.goto(`/history/${id}`);
  await expect(page.getByText(/not found|doesn.t exist|couldn.t/i).first()).toBeVisible();
  const token = await idToken(page);
  const res = await fetch(`http://127.0.0.1:8000/videos/${id}/compare/${id}x`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(res.status).toBe(404);
});

test("E. deleting the account removes the sign-in and every record it owned", async () => {
  await page.goto("/profile");
  await page.getByRole("button", { name: "Delete my account…" }).click();
  const confirm = page.getByRole("button", { name: "Delete everything permanently" });
  await expect(confirm).toBeDisabled(); // nothing happens without the phrase
  await page.getByLabel(/Type DELETE MY ACCOUNT/).fill("delete my account");
  await expect(confirm).toBeDisabled();
  await page.getByLabel(/Type DELETE MY ACCOUNT/).fill("DELETE MY ACCOUNT");
  await confirm.click();
  await expect(page).toHaveURL(/\/login/, { timeout: 60_000 });
  for (const collection of ["videos", "training_plans", "training_sessions", "training_state", "account_deletions"])
    expect(await adminOwned(collection, owner), collection).toHaveLength(0);
  expect(await adminExists(`profiles/${owner}`)).toBe(false);
  // the account is gone: signing in again fails
  await page.getByLabel("Email").fill(swimmer.email);
  await page.getByLabel("Password", { exact: true }).fill(swimmer.password);
  await page.getByRole("button", { name: "Log in" }).click();
  // by its text: Next's own route announcer is also an alert, so the role alone can match two
  await expect(page.getByText("Incorrect email or password")).toBeVisible();
  await expect(page).toHaveURL(/\/login/);
});

void signIn;
