// Runs once before any test: refuse to drive a site that is not AquaTrack.
//
// The config reuses a server that already answers on the chosen port. On a machine with
// several projects another app's dev server can be the one answering there, and the
// journeys would then type into a stranger's sign-up form. Nothing is clicked or typed
// until this check has passed.
import type { FullConfig } from "@playwright/test";

export default async function globalSetup(config: FullConfig) {
  const base = config.projects[0]?.use?.baseURL;
  if (!base) throw new Error("No baseURL configured.");
  let html = "";
  try {
    html = await (await fetch(`${base}/login`)).text();
  } catch {
    throw new Error(`Nothing answers at ${base}/login.`);
  }
  const title = /<title>([^<]*)<\/title>/i.exec(html)?.[1] ?? "";
  if (!/^aquatrack$/i.test(title.trim())) {
    throw new Error(
      `The server at ${base} is not AquaTrack (page title: "${title}"). Another project is ` +
        "using this port. Choose a free one with E2E_PORT and run again; do not stop the other server.",
    );
  }
}
