// Shared steps for the end-to-end journeys. Accounts are created through the app itself and
// exist only in the Auth emulator.
import { execFileSync } from "node:child_process";
import { existsSync } from "node:fs";
import path from "node:path";

import { expect, type Page } from "@playwright/test";

export const REPO = path.resolve(__dirname, "..", "..");
// A public test clip and pose data the real models produced for it earlier. Both are local,
// untracked files; the analysis journey is skipped when they are not on this machine.
export const PUBLIC_CLIP = path.join(REPO, "test_videos/public/front_crawl_underwater.webm");
export const HAS_FIXTURE =
  existsSync(PUBLIC_CLIP) && existsSync(path.join(REPO, "data/precomputed_pose"));

const DOCS =
  "http://127.0.0.1:8080/v1/projects/demo-aquatrack/databases/(default)/documents";
const ADMIN = { Authorization: "Bearer owner" }; // the emulator's admin token; not a secret

export type Swimmer = { email: string; password: string; name: string };

export function newSwimmer(): Swimmer {
  const id = `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 8)}`;
  return { email: `e2e-${id}@example.test`, password: `Pw-${id}-x9`, name: "Test Swimmer" };
}

export async function signUp(page: Page, s: Swimmer) {
  await page.goto("/signup");
  await page.getByLabel("Name").fill(s.name);
  await page.getByLabel("Email").fill(s.email);
  await page.getByLabel("Password", { exact: true }).fill(s.password);
  await page.getByLabel("Confirm password").fill(s.password);
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page).toHaveURL(/\/onboarding/);
}

export async function onboard(page: Page, goal = "Stroke consistency") {
  await page.getByLabel("Age").fill("30");
  await page.getByLabel("Height").fill("175");
  await page.getByLabel("Weight").fill("70");
  await page.getByRole("button", { name: "Continue" }).click();
  await page.getByText("Hobby", { exact: true }).click();
  await page.getByRole("button", { name: "Continue" }).click();
  await page.getByLabel("How many times do you train a week?").fill("3");
  await page.getByLabel("How much time do you spend swimming each day?").fill("45");
  await page.getByRole("button", { name: "Continue" }).click();
  await page.getByRole("button", { name: /Continue|Skip/ }).last().click(); // personal bests
  await page.getByText(goal, { exact: true }).click();
  await page.getByRole("button", { name: "Finish" }).click();
  await expect(page).toHaveURL(/localhost:\d+\/$/);
}

export async function signIn(page: Page, s: Swimmer) {
  await page.goto("/login");
  await page.getByLabel("Email").fill(s.email);
  await page.getByLabel("Password", { exact: true }).fill(s.password);
  await page.getByRole("button", { name: "Log in" }).click();
  await expect(page).toHaveURL(/localhost:\d+\/$/);
}

export async function uid(page: Page): Promise<string> {
  const token = await idToken(page);
  return JSON.parse(Buffer.from(token.split(".")[1], "base64").toString()).user_id;
}

// The signed-in swimmer's own ID token, read from the page's Firebase session.
export async function idToken(page: Page): Promise<string> {
  const token = await page.evaluate(async () => {
    const dbs = await indexedDB.databases();
    const name = dbs.find((d) => d.name?.includes("firebaseLocalStorage"))?.name;
    if (!name) return null;
    return await new Promise<string | null>((resolve) => {
      const open = indexedDB.open(name);
      open.onsuccess = () => {
        const all = open.result
          .transaction("firebaseLocalStorage")
          .objectStore("firebaseLocalStorage")
          .getAll();
        all.onsuccess = () =>
          resolve(all.result[0]?.value?.stsTokenManager?.accessToken ?? null);
      };
      open.onerror = () => resolve(null);
    });
  });
  if (!token) throw new Error("not signed in");
  return token;
}

// What is stored, read with the emulator's admin access (bypasses the security rules).
export async function adminList(collection: string): Promise<{ name: string; fields: Record<string, { stringValue?: string }> }[]> {
  const res = await fetch(`${DOCS}/${collection}?pageSize=300`, { headers: ADMIN });
  return ((await res.json()).documents ?? []) as never;
}

export async function adminOwned(collection: string, owner: string) {
  return (await adminList(collection)).filter((d) => d.fields?.uid?.stringValue === owner);
}

export async function adminExists(docPath: string): Promise<boolean> {
  return (await fetch(`${DOCS}/${docPath}`, { headers: ADMIN })).status === 200;
}

// Labelled SYNTHETIC analysed sessions for history and comparison (scripts/e2e_seed.py).
export function seedSyntheticSessions(owner: string): string[] {
  const out = execFileSync("uv", ["run", "python", "scripts/e2e_seed.py", owner], {
    cwd: REPO,
    encoding: "utf8",
  });
  return [...out.matchAll(/seeded (\S+)/g)].map((m) => m[1]);
}

export function localIso(d = new Date()): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}
