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
  if (href === "/history") return pathname.startsWith("/history") || pathname.startsWith("/feedback");
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
              className={`flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition ${
                active
                  ? "bg-white/15 text-white"
                  : "text-sky-100/80 hover:bg-white/10 hover:text-white"
              }`}
            >
              <Icon className="h-5 w-5" />
              {label}
            </Link>
          </li>
        );
      })}
    </ul>
  );

  const account = user && (
    <div className="flex items-center gap-3 border-t border-white/10 pt-4">
      <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-cyan-400/20 text-sm font-semibold text-cyan-100">
        {initials}
      </span>
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium text-white">{user.name}</p>
        <button onClick={logout} className="text-xs text-sky-200 hover:text-white">
          Log out
        </button>
      </div>
    </div>
  );

  return (
    <div className="flex min-h-screen flex-1 bg-slate-50">
      {/* Sidebar on laptops */}
      <aside className="sticky top-0 hidden h-screen w-64 shrink-0 flex-col justify-between overflow-hidden bg-gradient-to-b from-sky-900 to-sky-950 p-5 lg:flex">
        <div>
          <Link href="/" className="mb-8 block px-2 text-white">
            <Logo />
          </Link>
          <nav aria-label="Main">{navLinks}</nav>
        </div>
        <div className="relative z-10">{account}</div>
        <LaneLines />
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        {/* Top bar on phones and tablets */}
        <header className="sticky top-0 z-30 flex items-center justify-between bg-sky-900 px-4 py-3 text-white lg:hidden">
          <Link href="/">
            <Logo />
          </Link>
          <button
            onClick={() => setMenuOpen(true)}
            className="rounded-lg p-2 hover:bg-white/10"
            aria-label="Open menu"
          >
            <MenuIcon className="h-6 w-6" />
          </button>
        </header>

        {menuOpen && (
          <div className="fixed inset-0 z-40 lg:hidden" role="dialog" aria-modal="true">
            <button
              className="absolute inset-0 bg-slate-900/50"
              aria-label="Close menu"
              onClick={() => setMenuOpen(false)}
            />
            <div className="absolute inset-y-0 right-0 flex w-72 max-w-[85%] flex-col justify-between bg-sky-900 p-5">
              <div>
                <div className="mb-6 flex items-center justify-between text-white">
                  <Logo />
                  <button
                    onClick={() => setMenuOpen(false)}
                    className="rounded-lg p-2 hover:bg-white/10"
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
          className="fixed inset-x-0 bottom-0 z-30 grid grid-cols-5 border-t border-slate-200 bg-white/95 pb-[env(safe-area-inset-bottom)] backdrop-blur sm:hidden"
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
      className="pointer-events-none absolute inset-x-0 bottom-0 h-48 w-full text-white/[0.07]"
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
