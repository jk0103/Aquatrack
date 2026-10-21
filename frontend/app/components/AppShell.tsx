"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { onAuthStateChanged, signOut } from "firebase/auth";
import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

import {
  CalendarIcon,
  ChartIcon,
  CloseIcon,
  HistoryIcon,
  HomeIcon,
  MenuIcon,
  PlanIcon,
  UserIcon,
  VideoIcon,
} from "@/app/components/icons";
import { Logo } from "@/app/components/Logo";
import { ThemeToggle } from "@/app/components/ThemeToggle";
import { auth } from "@/app/lib/firebase";

const nav = [
  { href: "/", label: "Home", Icon: HomeIcon },
  { href: "/analyze", label: "Analyze a swim", Icon: VideoIcon },
  { href: "/training", label: "Training", Icon: PlanIcon },
  { href: "/calendar", label: "Calendar", Icon: CalendarIcon },
  { href: "/progress", label: "Progress", Icon: ChartIcon },
  { href: "/history", label: "History", Icon: HistoryIcon },
  { href: "/profile", label: "Profile", Icon: UserIcon },
];

export type User = { uid: string; name: string; email: string };

const UserContext = createContext<User | null>(null);

// The logged-in account, or null while it loads.
export function useUser() {
  return useContext(UserContext);
}

// The bottom tab bar on phones shows the most used pages; the menu has the rest.
const tabs = ["/", "/analyze", "/training", "/calendar", "/progress"];

function isActive(pathname: string, href: string) {
  if (href === "/") return pathname === "/";
  if (href === "/history")
    return pathname.startsWith("/history") || pathname.startsWith("/feedback");
  return pathname.startsWith(href);
}

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);

  useEffect(
    () =>
      onAuthStateChanged(auth, (firebaseUser) => {
        if (!firebaseUser) {
          router.replace("/login");
          return;
        }
        setUser({
          uid: firebaseUser.uid,
          name: firebaseUser.displayName ?? firebaseUser.email ?? "",
          email: firebaseUser.email ?? "",
        });
      }),
    [router],
  );

  async function logout() {
    await signOut(auth);
    router.replace("/login");
  }

  const initials = (user?.name ?? "")
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]!.toUpperCase())
    .join("");

  const navLinks = (
    <ul className="space-y-1">
      {nav.map(({ href, label, Icon }) => {
        const active = isActive(pathname, href);
        return (
          <li key={href}>
            <Link
              href={href}
              onClick={() => setMenuOpen(false)}
              aria-current={active ? "page" : undefined}
              className={`group relative flex items-center gap-3 overflow-hidden rounded-xl px-2 py-2 text-sm font-medium transition duration-300 ${
                active
                  ? "bg-sky-50 text-sky-800"
                  : "text-slate-600 hover:translate-x-0.5 hover:bg-slate-100 hover:text-slate-900"
              }`}
            >
              <span
                className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg transition duration-300 ${
                  active
                    ? "bg-sky-600 text-white shadow-sm"
                    : "bg-slate-100 text-slate-500 group-hover:bg-slate-200 group-hover:text-slate-700"
                }`}
              >
                <Icon className="h-[18px] w-[18px]" />
              </span>
              {label}
            </Link>
          </li>
        );
      })}
    </ul>
  );

  const account = user && (
    <div className="flex items-center gap-3 border-t border-slate-200/70 pt-4">
      <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-sky-100 text-sm font-semibold text-sky-800">
        {initials}
      </span>
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium text-slate-900">{user.name}</p>
        <button onClick={logout} className="tap-target -my-2 py-2 text-xs text-slate-500 hover:text-sky-700">
          Log out
        </button>
      </div>
    </div>
  );

  return (
    <div className="relative isolate flex min-h-screen flex-1 bg-slate-50 transition-colors duration-300">
      <WaterBackdrop />
      {/* Sidebar on laptops */}
      {/* Sidebar on laptops: frosted, so the page's water light shows through */}
      <aside className="sticky top-0 hidden h-screen w-64 shrink-0 flex-col justify-between overflow-hidden border-r border-slate-200/70 bg-surface/70 p-5 backdrop-blur-md lg:flex">
        <div className="relative">
          <Link href="/" className="mb-8 block px-2 text-sky-800">
            <Logo />
          </Link>
          <nav aria-label="Main">{navLinks}</nav>
        </div>
        <div className="relative z-10 space-y-4">
          <ThemeToggle className="w-fit" />
          {account}
        </div>
        <LaneLines />
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        {/* Top bar on phones and tablets */}
        <header className="sticky top-0 z-30 flex items-center justify-between border-b border-slate-200/70 bg-surface/85 px-4 py-3 backdrop-blur-md lg:hidden">
          <Link href="/" className="text-sky-800">
            <Logo />
          </Link>
          <div className="flex items-center gap-2">
            <ThemeToggle />
            <button
              onClick={() => setMenuOpen(true)}
              className="rounded-lg p-2 text-slate-700 hover:bg-slate-100"
              aria-label="Open menu"
            >
              <MenuIcon className="h-6 w-6" />
            </button>
          </div>
        </header>

        {menuOpen && (
          <div className="fixed inset-0 z-40 lg:hidden" role="dialog" aria-modal="true">
            <button
              className="absolute inset-0 bg-black/50"
              aria-label="Close menu"
              onClick={() => setMenuOpen(false)}
            />
            <div className="absolute inset-y-0 right-0 flex w-72 max-w-[85%] flex-col justify-between bg-surface p-5">
              <div>
                <div className="mb-6 flex items-center justify-between text-sky-800">
                  <Logo />
                  <button
                    onClick={() => setMenuOpen(false)}
                    className="rounded-lg p-2 text-slate-700 hover:bg-slate-100"
                    aria-label="Close menu"
                  >
                    <CloseIcon className="h-6 w-6" />
                  </button>
                </div>
                <nav aria-label="Main">{navLinks}</nav>
              </div>
              {account}
            </div>
          </div>
        )}

        <main className="mx-auto w-full max-w-6xl flex-1 px-4 pt-6 pb-28 sm:px-8 sm:pt-10 sm:pb-12">
          <UserContext.Provider value={user}>{children}</UserContext.Provider>
        </main>

        {/* Bottom tabs on phones */}
        <nav
          aria-label="Quick links"
          className="fixed inset-x-0 bottom-0 z-30 grid grid-cols-5 border-t border-slate-200 bg-surface/95 pb-[env(safe-area-inset-bottom)] backdrop-blur sm:hidden"
        >
          {nav
            .filter(({ href }) => tabs.includes(href))
            .map(({ href, label, Icon }) => {
              const active = isActive(pathname, href);
              return (
                <Link
                  key={href}
                  href={href}
                  className={`flex flex-col items-center gap-1 py-2 text-[11px] font-medium ${
                    active ? "text-sky-700" : "text-slate-500"
                  }`}
                >
                  <Icon className="h-5 w-5" />
                  {label === "Analyze a swim" ? "Analyze" : label}
                </Link>
              );
            })}
        </nav>
      </div>
    </div>
  );
}

function LaneLines() {
  return (
    <svg
      aria-hidden="true"
      className="pointer-events-none absolute inset-x-0 bottom-0 h-48 w-full text-sky-500/[0.08]"
      viewBox="0 0 200 150"
      preserveAspectRatio="none"
    >
      {[30, 70, 110, 150].map((y) => (
        <path
          key={y}
          d={`M0 ${y} Q25 ${y - 10} 50 ${y} T100 ${y} T150 ${y} T200 ${y}`}
          fill="none"
          stroke="currentColor"
          strokeWidth="3"
        />
      ))}
    </svg>
  );
}

// Soft, still colour behind every page so the frosted cards have something to blur.
function WaterBackdrop() {
  return (
    <div aria-hidden="true" className="pointer-events-none fixed inset-0 -z-10 overflow-hidden">
      <div className="absolute top-[-8%] left-[18%] h-[440px] w-[440px] rounded-full bg-sky-300/25 blur-3xl dark:bg-sky-500/10" />
      <div className="absolute top-[35%] right-[-6%] h-[480px] w-[480px] rounded-full bg-cyan-300/20 blur-3xl dark:bg-cyan-400/[0.06]" />
      <div className="absolute bottom-[-10%] left-[-4%] h-[400px] w-[400px] rounded-full bg-indigo-300/15 blur-3xl dark:bg-indigo-500/[0.08]" />
    </div>
  );
}
