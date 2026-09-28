export function Logo({ className = "" }: { className?: string }) {
  return (
    <span className={`inline-flex items-center gap-2 font-semibold tracking-tight ${className}`}>
      <svg viewBox="0 0 32 32" aria-hidden="true" className="h-8 w-8">
        <rect width="32" height="32" rx="9" fill="currentColor" opacity="0.14" />
        <path
          d="M5 13c3 0 3-2.5 5.5-2.5S13.5 13 16 13s3-2.5 5.5-2.5S24 13 27 13"
          fill="none"
          stroke="currentColor"
          strokeWidth="2.4"
          strokeLinecap="round"
        />
        <path
          d="M5 20c3 0 3-2.5 5.5-2.5S13.5 20 16 20s3-2.5 5.5-2.5S24 20 27 20"
          fill="none"
          stroke="currentColor"
          strokeWidth="2.4"
          strokeLinecap="round"
          opacity="0.6"
        />
      </svg>
      <span className="text-xl">Aquatrack</span>
    </span>
  );
}
