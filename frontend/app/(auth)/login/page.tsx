"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";

import { FormError, PasswordField, SubmitButton, TextField } from "@/app/components/fields";
import { api, type User } from "@/app/lib/api";
import { useFormSubmit } from "@/app/lib/useFormSubmit";

export default function LoginPage() {
  const router = useRouter();
  const { error, pending, onSubmit } = useFormSubmit(async (form) => {
    const result = await api<User>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email: form.get("email"), password: form.get("password") }),
    });
    if (!result.ok) return result.error;
    router.replace("/");
    return null;
  });

  return (
    <>
      <h1 className="text-2xl font-semibold tracking-tight text-slate-900">Welcome back</h1>
      <p className="mt-2 text-sm text-slate-600">Log in to see your latest swim analysis.</p>

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

      <p className="mt-8 text-center text-sm text-slate-600">
        New to Aquatrack?{" "}
        <Link href="/signup" className="font-semibold text-sky-700 hover:text-sky-900">
          Create an account
        </Link>
      </p>
    </>
  );
}
