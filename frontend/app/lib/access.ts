// Restricted deployments (the school demonstration): only accounts the backend was told to
// allow may use the app. These flags only shape the interface; the backend and the
// security rules do the enforcing.

import { api } from "@/app/lib/api";
import { auth } from "@/app/lib/firebase";

export const RESTRICTED = process.env.NEXT_PUBLIC_AQUATRACK_ACCESS === "restricted";
// The demonstration analyses one approved video from pose data extracted in advance.
export const DEMO = process.env.NEXT_PUBLIC_AQUATRACK_DEMO === "1";

const ACCESS_CLAIM = "aquatrack_demo"; // the claim firebase/restricted/*.rules require

export const ACCESS_DENIED =
  "This account isn't authorized for this AquaTrack demonstration.";

// Asks the backend whether the signed-in account may use this deployment.
// "unknown": the backend couldn't be reached, so nothing was decided.
export async function checkAccess(): Promise<"ok" | "denied" | "unknown"> {
  if (!RESTRICTED) return "ok";
  const res = await api<{ access: string }>("/access");
  if (!res.ok) return res.status === 403 ? "denied" : "unknown";
  // The security rules read the claim from the sign-in token. A token issued before the
  // claim was set doesn't carry it yet, so fetch a fresh one.
  const user = auth.currentUser;
  if (user) {
    const token = await user.getIdTokenResult();
    if (token.claims[ACCESS_CLAIM] !== true) await user.getIdToken(true);
  }
  return "ok";
}
