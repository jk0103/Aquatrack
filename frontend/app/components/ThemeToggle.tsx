"use client";

import { useSyncExternalStore } from "react";

// Light/dark switch. The choice is saved in this browser; until someone picks, the
// system setting decides (see the script in app/layout.tsx).

const KEY = "aquatrack-theme";

function subscribe(onChange: () => void) {
  const observer = new MutationObserver(onChange);
  observer.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });
  return () => observer.disconnect();
}

const isDark = () => document.documentElement.classList.contains("dark");

export function setTheme(dark: boolean) {
  document.documentElement.classList.toggle("dark", dark);
  try {
    localStorage.setItem(KEY, dark ? "dark" : "light");
  } catch {}
}

export function ThemeToggle({ className = "" }: { className?: string }) {
  const dark = useSyncExternalStore(subscribe, isDark, () => false);
  const options = [
    { value: false, label: "Light mode", icon: <SunIcon /> },
    { value: true, label: "Dark mode", icon: <MoonIcon /> },
  ];
  return (
    <div
      role="group"
      aria-label="Colour theme"
      className={`relative flex rounded-full bg-slate-100 p-1 ring-1 ring-slate-200 ${className}`}
    >
      <span
        aria-hidden="true"
        className={`absolute top-1 bottom-1 left-1 w-9 rounded-full bg-surface shadow transition-transform duration-300 ease-[cubic-bezier(0.22,1,0.36,1)] ${
          dark ? "translate-x-9" : ""
        }`}
      />
      {options.map((o) => (
        <button
          key={o.label}
          onClick={() => setTheme(o.value)}
          aria-pressed={dark === o.value}
          aria-label={o.label}
          title={o.label}
          className={`tap-target relative flex h-8 w-9 items-center justify-center rounded-full transition-colors duration-300 ${
            dark === o.value ? "text-sky-700" : "text-slate-500 hover:text-slate-800"
          }`}
        >
          {o.icon}
        </button>
      ))}
    </div>
  );
}

function SunIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      className="h-4 w-4"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      aria-hidden="true"
    >
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
    </svg>
  );
}

function MoonIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      className="h-4 w-4"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z" />
    </svg>
  );
}
