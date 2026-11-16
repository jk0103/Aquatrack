// Start the Firebase Emulator Suite (Auth, Firestore, Storage) for local development.
// firebase-tools needs Java 21 or newer. If the default `java` is older, this picks a newer
// JDK that is already installed, for this process only (nothing system-wide changes).
// Override with AQUATRACK_JAVA_HOME=/path/to/jdk.
import { execFileSync, spawn, spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import path from "node:path";

// `java -version` prints to stderr; 0 means java is missing.
function javaMajor() {
  const res = spawnSync("java", ["-version"], { encoding: "utf8" });
  return Number(/version "(\d+)/.exec(`${res.stderr ?? ""}${res.stdout ?? ""}`)?.[1] ?? 0);
}

function newerJavaHome() {
  if (process.env.AQUATRACK_JAVA_HOME) return process.env.AQUATRACK_JAVA_HOME;
  try {
    // macOS: the newest installed JDK that is at least 21
    return execFileSync("/usr/libexec/java_home", ["-v", "21+"], { encoding: "utf8" }).trim();
  } catch {
    return null;
  }
}

const env = { ...process.env };
const current = javaMajor();
if (current < 21) {
  const home = newerJavaHome();
  if (!home || !existsSync(path.join(home, "bin", "java"))) {
    console.error("Firebase emulators need Java 21+. Install a JDK or set AQUATRACK_JAVA_HOME.");
    process.exit(1);
  }
  env.JAVA_HOME = home;
  env.PATH = `${path.join(home, "bin")}${path.delimiter}${env.PATH}`;
  console.log(`Using the JDK at ${home} (default java is ${current || "missing"}).`);
}

// `--restricted` loads the restricted rules (firebase/restricted/), to rehearse the
// account-restricted demonstration locally. Still the emulators, still the demo- project.
const config = process.argv.includes("--restricted")
  ? "../firebase.restricted.json"
  : "../firebase.json";
const child = spawn(
  "firebase",
  ["emulators:start", "--project", "demo-aquatrack", "--config", config],
  { stdio: "inherit", env },
);
child.on("exit", (code) => process.exit(code ?? 0));
for (const signal of ["SIGINT", "SIGTERM"]) process.on(signal, () => child.kill(signal));
