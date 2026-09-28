"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { Logo } from "@/app/components/Logo";
import { api, type User } from "@/app/lib/api";

// Placeholder home until the upload and results screens exist.
export default function HomePage() {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);

  useEffect(() => {
    api<User>("/auth/me").then(async (result) => {
      if (result.ok) {
        setUser(result.data);
      } else {
        // Stale or invalid cookie: clear it so the login page doesn't bounce back here.
        await api("/auth/logout", { method: "POST" });
        router.replace("/login");
      }
    });
  }, [router]);

  async function logout() {
    await api("/auth/logout", { method: "POST" });
    router.replace("/login");
  }

  return (
    <div className="flex min-h-screen flex-1 flex-col bg-slate-50">
      <header className="flex items-center justify-between border-b border-slate-200 bg-white px-4 py-3 sm:px-8">
        <Logo className="text-sky-800" />
        {user && (
          <button
            onClick={logout}
            className="rounded-lg px-3 py-2 text-sm font-medium text-slate-600 hover:bg-slate-100 hover:text-slate-900"
          >
            Log out
          </button>
        )}
      </header>
      <main className="mx-auto w-full max-w-3xl flex-1 px-4 py-12 sm:px-8">
        {user ? (
          <>
            <h1 className="text-3xl font-semibold tracking-tight text-slate-900">
              Hi, {user.name}
            </h1>
            <p className="mt-3 text-slate-600">
              You&apos;re logged in as {user.email}. Video upload and analysis are coming next.
            </p>
          </>
        ) : (
          <p className="text-slate-500">Loading…</p>
        )}
      </main>
    </div>
  );
}
