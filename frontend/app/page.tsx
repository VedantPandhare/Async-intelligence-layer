import Link from "next/link";

const features = [
  {
    title: "Signal collection",
    description:
      "Unifies commit activity, PR reviews, CI runs, Slack messages, and Jira updates into normalized developer signals.",
    icon: (
      <svg className="w-4 h-4 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
          d="M13 10V3L4 14h7v7l9-11h-7z" />
      </svg>
    ),
  },
  {
    title: "Blocker detection",
    description:
      "LangGraph agents analyze signal patterns to identify friction, stale PRs, failed pipelines, and developer blockers.",
    icon: (
      <svg className="w-4 h-4 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
          d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
      </svg>
    ),
  },
  {
    title: "Smart digests",
    description:
      "Daily markdown reports with developer narratives, coordination flags, and sprint health — delivered to Slack or email.",
    icon: (
      <svg className="w-4 h-4 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
          d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
      </svg>
    ),
  },
];

export default function LandingPage() {
  return (
    <div className="min-h-screen bg-slate-950 text-slate-50 flex flex-col">
      {/* Header */}
      <header className="fixed top-0 inset-x-0 z-50 h-14 border-b border-white/5 bg-slate-950/80 backdrop-blur-md">
        <div className="max-w-5xl mx-auto px-6 h-full flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="w-6 h-6 bg-white rounded flex items-center justify-center shrink-0">
              <svg className="w-3.5 h-3.5 text-slate-950" fill="currentColor" viewBox="0 0 24 24">
                <path d="M13 10V3L4 14h7v7l9-11h-7z" />
              </svg>
            </div>
            <span className="text-sm font-semibold tracking-tight">Async Intel</span>
          </div>
          <nav className="flex items-center gap-1">
            <Link
              href="/login"
              className="px-4 py-1.5 text-sm text-slate-400 hover:text-white transition-colors rounded-lg hover:bg-white/5"
            >
              Sign in
            </Link>
            <Link
              href="/register"
              className="px-4 py-1.5 text-sm bg-white text-slate-950 hover:bg-slate-100 transition-colors rounded-lg font-medium"
            >
              Get started
            </Link>
          </nav>
        </div>
      </header>

      {/* Hero */}
      <main className="flex-1 flex flex-col items-center justify-center px-6 pt-28 pb-16 text-center">
        <div className="inline-flex items-center gap-2 text-xs text-slate-500 border border-white/10 rounded-full px-3 py-1 mb-10">
          <span className="w-1.5 h-1.5 rounded-full bg-green-400 animate-pulse shrink-0" />
          LangGraph · GitHub · Slack · Jira · FastAPI
        </div>

        <h1 className="text-5xl sm:text-6xl font-bold tracking-tighter leading-[1.05] mb-6 max-w-3xl">
          Engineering intelligence{" "}
          <span className="text-slate-500">for async teams.</span>
        </h1>

        <p className="text-lg text-slate-400 max-w-xl leading-relaxed mb-10">
          Replace daily standups with AI-powered signal analysis. Automated
          digests, blocker detection, and coordination insights — all from your
          team&apos;s existing activity.
        </p>

        <div className="flex flex-wrap items-center justify-center gap-3">
          <Link
            href="/register"
            className="inline-flex items-center gap-2 bg-white text-slate-950 hover:bg-slate-100 font-medium px-6 py-2.5 rounded-lg text-sm transition-colors"
          >
            Get started for free
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
            </svg>
          </Link>
          <Link
            href="/login"
            className="inline-flex items-center gap-2 text-slate-400 hover:text-white px-6 py-2.5 rounded-lg text-sm transition-colors hover:bg-white/5"
          >
            Sign in to workspace
          </Link>
        </div>
      </main>

      {/* Features */}
      <section className="px-6 pb-20 max-w-5xl mx-auto w-full">
        <div className="grid grid-cols-1 md:grid-cols-3 divide-y md:divide-y-0 md:divide-x divide-white/5 border border-white/5 rounded-2xl overflow-hidden">
          {features.map((f) => (
            <div key={f.title} className="p-7 bg-slate-900/40 hover:bg-slate-900/80 transition-colors">
              <div className="w-8 h-8 bg-slate-800 border border-slate-700 rounded-lg flex items-center justify-center mb-5">
                {f.icon}
              </div>
              <h3 className="text-sm font-semibold text-white mb-2">{f.title}</h3>
              <p className="text-sm text-slate-500 leading-relaxed">{f.description}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-white/5 py-6 px-6">
        <div className="max-w-5xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <div className="w-5 h-5 bg-white rounded flex items-center justify-center shrink-0">
              <svg className="w-3 h-3 text-slate-950" fill="currentColor" viewBox="0 0 24 24">
                <path d="M13 10V3L4 14h7v7l9-11h-7z" />
              </svg>
            </div>
            <span className="text-xs text-slate-600 font-medium">Async Intel</span>
          </div>
          <span className="text-xs text-slate-700">Built with LangGraph · FastAPI · Next.js</span>
        </div>
      </footer>
    </div>
  );
}
