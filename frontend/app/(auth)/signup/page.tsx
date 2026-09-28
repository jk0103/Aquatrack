"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";

import { FormError, PasswordField, SubmitButton, TextField } from "@/app/components/fields";
import { api, type User } from "@/app/lib/api";
import { useFormSubmit } from "@/app/lib/useFormSubmit";

const MIN_PASSWORD = 8;

export default function SignupPage() {
  const router = useRouter();
  const { error, pending, onSubmit } = useFormSubmit(async (form) => {
    const name = String(form.get("name") ?? "").trim();
    const email = String(form.get("email") ?? "").trim();
    const password = String(form.get("password") ?? "");

    if (!name) return "Enter your name.";
    if (!email.includes("@")) return "Enter a valid email address.";
    if (password.length < MIN_PASSWORD) {
      return `Password must be at least ${MIN_PASSWORD} characters.`;
    }
    if (password !== form.get("confirm")) return "Passwords don't match.";

    const result = await api<User>("/auth/signup", {
      method: "POST",
      body: JSON.stringify({ name, email, password }),
    });
    if (!result.ok) return result.error;
    router.replace("/");
    return null;
  });

  return (
    <>
      <h1 className="text-2xl font-semibold tracking-tight text-slate-900">Create your account</h1>
      <p className="mt-2 text-sm text-slate-600">
        Upload your swims and get feedback on your technique.
      </p>

      <form onSubmit={onSubmit} className="mt-8 space-y-5" noValidate>
        <FormError message={error} />
        <TextField label="Name" name="name" autoComplete="name" placeholder="Your name" required />
        <TextField
          label="Email"
          name="email"
          type="email"
          autoComplete="email"
          placeholder="you@example.com"
          required
        />
        <PasswordField
          label="Password"
          name="password"
          autoComplete="new-password"
          hint={`At least ${MIN_PASSWORD} characters`}
          minLength={MIN_PASSWORD}
          required
        />
        <PasswordField
          label="Confirm password"
          name="confirm"
          autoComplete="new-password"
          required
        />
        <SubmitButton pending={pending}>Create account</SubmitButton>
      </form>

      <p className="mt-8 text-center text-sm text-slate-600">
        Already have an account?{" "}
        <Link href="/login" className="font-semibold text-sky-700 hover:text-sky-900">
          Log in
        </Link>
      </p>
    </>
  );
}
