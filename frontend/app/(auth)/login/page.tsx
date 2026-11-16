"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { signInWithEmailAndPassword, signOut } from "firebase/auth";

import { ACCESS_DENIED, checkAccess, RESTRICTED } from "@/app/lib/access";
import { FormError, PasswordField, SubmitButton, TextField } from "@/app/components/fields";
import { auth, describeFirebaseError } from "@/app/lib/firebase";
import { useFormSubmit } from "@/app/lib/useFormSubmit";

export default function LoginPage() {
  const router = useRouter();
  const { error, pending, onSubmit } = useFormSubmit(async (form) => {
    const email = String(form.get("email") ?? "").trim();
    const password = String(form.get("password") ?? "");
    if (!email || !password) return "Enter your email and password.";
    try {
      await signInWithEmailAndPassword(auth, email, password);
    } catch (err) {
      return describeFirebaseError(err);
    }
    // A restricted deployment admits only the accounts the backend allows.
    const access = await checkAccess();
    if (access !== "ok") {
      await signOut(auth);
      return access === "denied"
        ? ACCESS_DENIED
        : "Couldn't confirm this account's access. Wait a moment and try again.";
    }
    router.replace("/");
    return null;
  });

  return (
    <>
      <h1 className="text-3xl font-semibold tracking-tight text-slate-900">Welcome back</h1>

      <form onSubmit={onSubmit} className="mt-8 space-y-5" noValidate>
        <FormError message={error} />
        <TextField
          label="Email"
          name="email"
          type="email"
          autoComplete="email"
          placeholder="you@example.com"
          required
        />
        <PasswordField label="Password" name="password" autoComplete="current-password" required />
        <SubmitButton pending={pending}>Log in</SubmitButton>
      </form>

      {RESTRICTED ? (
        <p className="mt-8 text-center text-sm text-slate-600">
          This demonstration is open to invited accounts only. Sign-up is closed.
        </p>
      ) : (
        <p className="mt-8 text-center text-sm text-slate-600">
          New to Aquatrack?{" "}
          <Link href="/signup" className="font-semibold text-sky-700 hover:text-sky-900">
            Create an account
          </Link>
        </p>
      )}
    </>
  );
}
