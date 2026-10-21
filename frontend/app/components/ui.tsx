import Link from "next/link";
import type { CSSProperties, ReactNode } from "react";

import { ArrowUpRightIcon } from "@/app/components/icons";

export function PageHeader({
  title,
  subtitle,
  action,
}: {
  title: string;
  subtitle?: string;
  action?: ReactNode;
}) {
  return (
    <div className="mb-6 flex flex-col gap-4 sm:mb-8 sm:flex-row sm:items-end sm:justify-between">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-slate-900 sm:text-3xl">
          {title}
        </h1>
        {subtitle && <p className="mt-1.5 text-slate-600">{subtitle}</p>}
      </div>
      {action}
    </div>
  );
}

export function Card({
  title,
  action,
  children,
  className = "",
}: {
  title?: string;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`rounded-2xl glass p-5 sm:p-6 ${className}`}>
      {title && (
        <div className="mb-4 flex items-center justify-between gap-3">
          <h2 className="font-semibold text-slate-900">{title}</h2>
          {action}
        </div>
      )}
      {children}
    </section>
  );
}

export function CardLink({ href, children }: { href: string; children: ReactNode }) {
  return (
    <Link href={href} className="text-sm font-medium text-sky-700 hover:text-sky-900">
      {children}
    </Link>
  );
}

const buttonStyles = {
  primary: "bg-sky-700 text-white shadow-sm hover:bg-sky-800 focus:ring-sky-600/30",
  secondary:
    "border border-slate-300 bg-surface text-slate-700 shadow-sm hover:bg-slate-50 focus:ring-sky-600/15",
};

export function ButtonLink({
  href,
  children,
  variant = "primary",
}: {
  href: string;
  children: ReactNode;
  variant?: keyof typeof buttonStyles;
}) {
  return (
    <Link
      href={href}
      className={`inline-flex items-center justify-center gap-2 rounded-lg px-4 py-2.5 text-sm font-semibold transition focus:outline-none focus:ring-4 ${buttonStyles[variant]}`}
    >
      {children}
    </Link>
  );
}

export function Button({
  children,
  variant = "primary",
  type = "button",
  className = "",
  onClick,
}: {
  children: ReactNode;
  variant?: keyof typeof buttonStyles;
  type?: "button" | "submit";
  className?: string;
  onClick?: () => void;
}) {
  return (
    <button
      type={type}
      onClick={onClick}
      className={`inline-flex items-center justify-center gap-2 rounded-lg px-4 py-2.5 text-sm font-semibold transition focus:outline-none focus:ring-4 ${buttonStyles[variant]} ${className}`}
    >
      {children}
    </button>
  );
}

const badgeTones = {
  sky: "bg-sky-50 text-sky-700 ring-sky-600/20",
  teal: "bg-teal-50 text-teal-700 ring-teal-600/20",
  indigo: "bg-indigo-50 text-indigo-700 ring-indigo-600/20",
  amber: "bg-amber-50 text-amber-800 ring-amber-600/20",
  slate: "bg-slate-100 text-slate-600 ring-slate-500/20",
};

export function Badge({
  children,
  tone = "sky",
}: {
  children: ReactNode;
  tone?: keyof typeof badgeTones;
}) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ring-inset ${badgeTones[tone]}`}
    >
      {children}
    </span>
  );
}

// A smooth progress bar that fills from empty when the page opens.
export function LaneProgress({ value, label }: { value: number; label: string }) {
  const pct = Math.max(0, Math.min(100, value));
  return (
    <div
      role="progressbar"
      aria-label={label}
      aria-valuenow={Math.round(pct)}
      aria-valuemin={0}
      aria-valuemax={100}
      className="h-2.5 overflow-hidden rounded-full bg-slate-200 ring-1 ring-slate-300/70 ring-inset"
    >
      <div
        className="bar-fill h-full rounded-full bg-gradient-to-r from-sky-600 to-cyan-400"
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}

export function Stat({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <div className="rounded-2xl glass p-4 sm:p-5">
      <p className="text-sm text-slate-500">{label}</p>
      <p className="mt-1 text-2xl font-semibold tracking-tight text-slate-900">{value}</p>
      {note && <p className="mt-1 text-xs font-medium text-teal-700">{note}</p>}
    </div>
  );
}

// A water-coloured stand-in where a video or frame will go.
export function VideoPlaceholder({ label, className = "" }: { label: string; className?: string }) {
  return (
    <div
      className={`relative flex aspect-video items-center justify-center overflow-hidden rounded-xl bg-gradient-to-b from-sky-800 to-cyan-900 ${className}`}
    >
      <svg
        aria-hidden="true"
        viewBox="0 0 400 225"
        preserveAspectRatio="none"
        className="absolute inset-0 h-full w-full text-white/10"
      >
        {[45, 112, 180].map((y) => (
          <path
            key={y}
            d={`M0 ${y} Q50 ${y - 10} 100 ${y} T200 ${y} T300 ${y} T400 ${y}`}
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
          />
        ))}
      </svg>
      <span className="relative flex h-14 w-14 items-center justify-center rounded-full bg-white/90 text-sky-800 shadow-lg">
        <svg viewBox="0 0 24 24" className="ml-1 h-6 w-6" fill="currentColor" aria-hidden="true">
          <path d="M8 5.5v13l10-6.5z" />
        </svg>
      </span>
      <span className="absolute bottom-3 left-3 rounded-md bg-black/40 px-2 py-1 text-xs text-white">
        {label}
      </span>
    </div>
  );
}

export function DateChip({ iso, meet = false }: { iso: string; meet?: boolean }) {
  const d = new Date(`${iso}T00:00:00`);
  return (
    <span
      className={`flex h-12 w-12 shrink-0 flex-col items-center justify-center rounded-xl ${
        meet ? "bg-indigo-50 text-indigo-700" : "bg-sky-50 text-sky-700"
      }`}
    >
      <span className="text-[10px] font-semibold uppercase">
        {d.toLocaleDateString("en-US", { month: "short" })}
      </span>
      <span className="text-lg font-semibold leading-none">{d.getDate()}</span>
    </span>
  );
}

// Frosted glass panel with an icon chip, a title and an optional ↗ link, used on the Home
// page over its water backdrop. `glow` tints the light in the top-right corner.
export function GlassCard({
  title,
  icon,
  href,
  linkLabel,
  glow,
  className = "",
  children,
}: {
  title?: string;
  icon?: ReactNode;
  href?: string;
  linkLabel?: string;
  glow?: string;
  className?: string;
  children: ReactNode;
}) {
  return (
    <section
      className={`glass glass-glow rounded-2xl p-5 sm:p-6 ${className}`}
      style={glow ? ({ "--glow": glow } as CSSProperties) : undefined}
    >
      {title && (
        <div className="mb-4 flex items-center gap-3">
          {icon && (
            <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-sky-50 text-sky-700">
              {icon}
            </span>
          )}
          <h2 className="flex-1 font-semibold text-slate-900">{title}</h2>
          {href && (
            <Link
              href={href}
              aria-label={linkLabel ?? title}
              className="tap-target flex h-9 w-9 items-center justify-center rounded-full text-slate-500 ring-1 ring-slate-200 transition duration-300 hover:-translate-y-0.5 hover:translate-x-0.5 hover:bg-slate-50 hover:text-sky-700"
            >
              <ArrowUpRightIcon className="h-4 w-4" />
            </Link>
          )}
        </div>
      )}
      {children}
    </section>
  );
}

export { ArcGauge } from "@/app/components/ArcGauge";

// Marks placeholder numbers so nobody mistakes them for their own results.
export function ExampleNote({ children }: { children: ReactNode }) {
  return (
    <p className="flex items-start gap-2 rounded-xl bg-amber-50 px-3.5 py-2.5 text-sm text-amber-900">
      <span className="mt-0.5 shrink-0 rounded-full bg-amber-100 px-2 text-xs font-semibold">
        Example
      </span>
      <span>{children}</span>
    </p>
  );
}
