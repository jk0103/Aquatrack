import { Logo } from "@/app/components/Logo";

const highlights = [
  "Analyze underwater and overhead swim video",
  "Feedback shaped by your goals, records and history",
  "See how your stroke changes session to session",
];

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen flex-1 bg-white">
      <aside className="relative hidden w-[44%] overflow-hidden bg-gradient-to-br from-sky-900 via-sky-800 to-cyan-700 p-12 text-white lg:flex lg:flex-col lg:justify-between">
        <Logo />
        <div className="relative z-10 max-w-md">
          <h2 className="text-4xl font-semibold leading-tight">See your stroke. Swim faster.</h2>
          <ul className="mt-8 space-y-4 text-sky-100">
            {highlights.map((text) => (
              <li key={text} className="flex gap-3">
                <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-cyan-300" />
                {text}
              </li>
            ))}
          </ul>
        </div>
        <p className="relative z-10 text-sm text-sky-200">
          Personalized swim technique feedback
        </p>
        {/* Lane lines */}
        <svg
          aria-hidden="true"
          className="pointer-events-none absolute inset-x-0 bottom-0 h-64 w-full text-white/10"
          viewBox="0 0 400 200"
          preserveAspectRatio="none"
        >
          {[40, 90, 140, 190].map((y) => (
            <path
              key={y}
              d={`M0 ${y} Q50 ${y - 14} 100 ${y} T200 ${y} T300 ${y} T400 ${y}`}
              fill="none"
              stroke="currentColor"
              strokeWidth="3"
            />
          ))}
        </svg>
      </aside>

      <main className="flex flex-1 flex-col items-center justify-center px-4 py-12 sm:px-8">
        <Logo className="mb-10 text-sky-800 lg:hidden" />
        <div className="w-full max-w-sm">{children}</div>
      </main>
    </div>
  );
}
