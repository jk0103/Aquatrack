// Firebase client: login (Auth), profile and video records (Firestore), video files (Storage).
// Settings come from frontend/.env.local (see .env.local.example).

import { getApp, getApps, initializeApp } from "firebase/app";
import { connectAuthEmulator, getAuth } from "firebase/auth";
import { connectFirestoreEmulator, getFirestore } from "firebase/firestore";
import { connectStorageEmulator, getStorage } from "firebase/storage";

// Local emulators (npm run emulators) need no real project or keys.
const useEmulators = process.env.NEXT_PUBLIC_FIREBASE_EMULATORS === "true";

const apiKey = process.env.NEXT_PUBLIC_FIREBASE_API_KEY || (useEmulators ? "demo-key" : "");
export const firebaseConfigured = Boolean(apiKey);

if (!firebaseConfigured && typeof window !== "undefined") {
  console.error(
    "Firebase isn't configured. Copy frontend/.env.local.example to frontend/.env.local and fill it in.",
  );
}

const config = {
  // A placeholder keeps pages building without a config; Firebase calls then fail clearly.
  apiKey: apiKey || "not-configured",
  authDomain: process.env.NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN,
  projectId:
    process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID || (useEmulators ? "demo-aquatrack" : undefined),
  storageBucket:
    process.env.NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET ||
    (useEmulators ? "demo-aquatrack.appspot.com" : undefined),
  messagingSenderId: process.env.NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID,
  appId: process.env.NEXT_PUBLIC_FIREBASE_APP_ID,
};

const app = getApps().length ? getApp() : initializeApp(config);

export const auth = getAuth(app);
export const db = getFirestore(app);
export const storage = getStorage(app);

// Connect once, even when hot reload re-runs this module.
const flag = globalThis as { __aquatrackEmulators?: boolean };
if (useEmulators && !flag.__aquatrackEmulators) {
  flag.__aquatrackEmulators = true;
  connectAuthEmulator(auth, "http://127.0.0.1:9099", { disableWarnings: true });
  connectFirestoreEmulator(db, "127.0.0.1", 8080);
  connectStorageEmulator(storage, "127.0.0.1", 9199);
}

// Turns Firebase error codes into messages people can act on.
export function describeFirebaseError(err: unknown): string {
  const code = (err as { code?: string })?.code ?? "";
  if (!firebaseConfigured) {
    return "Firebase isn't set up yet. Add its settings to frontend/.env.local.";
  }
  switch (code) {
    case "auth/invalid-credential":
    case "auth/wrong-password":
    case "auth/user-not-found":
      return "Incorrect email or password";
    case "auth/email-already-in-use":
      return "An account with this email already exists";
    case "auth/invalid-email":
      return "Enter a valid email address.";
    case "auth/weak-password":
      return "Password must be at least 8 characters.";
    case "auth/too-many-requests":
      return "Too many attempts. Wait a minute and try again.";
    case "auth/network-request-failed":
    case "unavailable":
      return "Can't reach the server. Check your connection.";
    case "permission-denied":
    case "storage/unauthorized":
      return "You don't have permission to do that. Try logging in again.";
    default:
      return "Something went wrong. Try again.";
  }
}
