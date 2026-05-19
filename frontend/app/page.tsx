"use client";

import { useState } from "react";
import Link from "next/link";

// ─── Animated gradient bars (same mechanic as the reference) ──────────────────

function GradientBars() {
  const NUM = 18;
  const calcScale = (i: number) => {
    const pos = i / (NUM - 1);
    const dist = Math.abs(pos - 0.5);
    return 0.28 + 0.72 * Math.pow(dist * 2, 1.15);
  };

  return (
    <div className="absolute inset-0 z-0 overflow-hidden pointer-events-none">
      <div className="flex h-full w-full">
        {Array.from({ length: NUM }).map((_, i) => (
          <div
            key={i}
            style={{
              flex: `1 0 ${100 / NUM}%`,
              maxWidth: `${100 / NUM}%`,
              height: "100%",
              background: "linear-gradient(to top, rgb(255, 60, 0), transparent)",
              transform: `scaleY(${calcScale(i)})`,
              transformOrigin: "bottom",
              animation: "pulseBar 2.2s ease-in-out infinite alternate",
              animationDelay: `${i * 0.09}s`,
            }}
          />
        ))}
      </div>
    </div>
  );
}

// ─── Navbar ────────────────────────────────────────────────────────────────────

function Navbar() {
  const [open, setOpen] = useState(false);

  return (
    <nav className="fixed top-0 left-0 right-0 z-50 py-5 px-6 md:px-12">
      <div className="max-w-6xl mx-auto">
        <div className="flex justify-between items-center">
          {/* Logo */}
          <Link href="/" className="flex items-center gap-2.5">
            <div className="w-6 h-6 bg-white rounded flex items-center justify-center shrink-0">
              <svg className="w-3.5 h-3.5 text-gray-950" fill="currentColor" viewBox="0 0 24 24">
                <path d="M13 10V3L4 14h7v7l9-11h-7z" />
              </svg>
            </div>
            <span className="text-white font-semibold tracking-tight text-sm">StandOut</span>
          </Link>

          {/* Desktop */}
          <div className="hidden md:flex items-center gap-7">
            <a href="#features" className="text-gray-400 hover:text-white transition-colors duration-200 text-sm">
              Features
            </a>
            <a href="#how-it-works" className="text-gray-400 hover:text-white transition-colors duration-200 text-sm">
              How it works
            </a>
            <Link href="/login" className="text-gray-400 hover:text-white transition-colors duration-200 text-sm">
              Sign in
            </Link>
            <Link
              href="/register"
              className="bg-white hover:bg-gray-100 text-gray-950 px-5 py-2 rounded-full transition-all duration-300 hover:scale-105 text-sm font-medium"
            >
              Get started
            </Link>
          </div>

          {/* Mobile toggle */}
          <button onClick={() => setOpen(!open)} className="md:hidden text-white p-1">
            {open ? (
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            ) : (
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
              </svg>
            )}
          </button>
        </div>

        {/* Mobile menu */}
        {open && (
          <div className="md:hidden mt-4 bg-gray-900/95 backdrop-blur-md rounded-2xl p-5 border border-white/5 animate-fadeIn">
            <div className="flex flex-col gap-4">
              <a href="#features" onClick={() => setOpen(false)} className="text-gray-300 hover:text-white transition-colors text-sm py-1">
                Features
              </a>
              <a href="#how-it-works" onClick={() => setOpen(false)} className="text-gray-300 hover:text-white transition-colors text-sm py-1">
                How it works
              </a>
              <Link href="/login" className="text-gray-300 hover:text-white transition-colors text-sm py-1">
                Sign in
              </Link>
              <Link href="/register" className="bg-white text-gray-950 px-5 py-2.5 rounded-full text-sm font-medium text-center mt-1">
                Get started
              </Link>
            </div>
          </div>
        )}
      </div>
    </nav>
  );
}

// ─── Integration pill ─────────────────────────────────────────────────────────

function IntegrationBadge() {
  return (
    <div
      className="inline-flex items-center gap-3 bg-gray-900/60 backdrop-blur-sm rounded-full py-2 px-4 text-sm animate-fadeIn"
      style={{ animationDelay: "100ms" }}
    >
      <span className="w-1.5 h-1.5 rounded-full bg-green-400 animate-pulse shrink-0" />
      <span className="text-gray-300">
        Integrates with{" "}
        <span className="text-white font-semibold">GitHub · Slack · Jira</span>
      </span>
    </div>
  );
}

// ─── Features section ─────────────────────────────────────────────────────────

const FEATURES = [
  {
    title: "Signal collection",
    desc: "Normalises commits, PR reviews, CI runs, Slack messages, and Jira updates into unified developer signals — automatically.",
    icon: (
      <svg className="w-5 h-5 text-orange-500/70" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M13 10V3L4 14h7v7l9-11h-7z" />
      </svg>
    ),
  },
  {
    title: "AI blocker detection",
    desc: "LangGraph agents scan signal patterns to surface stale PRs, failed pipelines, and developer friction before they become blockers.",
    icon: (
      <svg className="w-5 h-5 text-orange-500/70" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17H3a2 2 0 01-2-2V5a2 2 0 012-2h16a2 2 0 012 2v10a2 2 0 01-2 2h-2" />
      </svg>
    ),
  },
  {
    title: "Smart digests",
    desc: "Daily markdown reports with per-developer narratives, coordination flags, and sprint health summaries — delivered to Slack or email.",
    icon: (
      <svg className="w-5 h-5 text-orange-500/70" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
      </svg>
    ),
  },
  {
    title: "Dependency conflicts",
    desc: "Detects when multiple engineers are touching the same files or services and surfaces coordination risk before merge conflicts occur.",
    icon: (
      <svg className="w-5 h-5 text-orange-500/70" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4" />
      </svg>
    ),
  },
  {
    title: "Developer timelines",
    desc: "Per-developer activity views across 8h, 24h, 48h, and 7-day windows. Understand who is shipping and who might be stuck.",
    icon: (
      <svg className="w-5 h-5 text-orange-500/70" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
    ),
  },
  {
    title: "Proactive interventions",
    desc: "When a critical blocker is detected the pipeline can automatically send a Slack DM to the affected developer or their manager.",
    icon: (
      <svg className="w-5 h-5 text-orange-500/70" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" />
      </svg>
    ),
  },
];

function FeaturesSection() {
  return (
    <section id="features" className="bg-slate-950 py-28 px-6 border-t border-white/5">
      <div className="max-w-5xl mx-auto">
        <div className="text-center mb-16">
          <span className="text-xs text-gray-600 uppercase tracking-[0.2em] font-medium">Features</span>
          <h2 className="text-3xl font-bold tracking-tight text-white mt-3 mb-4">
            Everything your team needs
          </h2>
          <p className="text-gray-500 text-base max-w-xl mx-auto leading-relaxed">
            The full intelligence stack — from raw activity ingestion to actionable daily reports.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-px bg-white/5 rounded-2xl overflow-hidden border border-white/5">
          {FEATURES.map((f) => (
            <div
              key={f.title}
              className="bg-slate-950 hover:bg-slate-900/80 transition-colors p-7 group"
            >
              <div className="w-9 h-9 bg-slate-900 border border-white/8 rounded-xl flex items-center justify-center mb-5 group-hover:border-orange-500/20 transition-colors">
                {f.icon}
              </div>
              <h3 className="text-sm font-semibold text-white mb-2">{f.title}</h3>
              <p className="text-sm text-gray-500 leading-relaxed">{f.desc}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

// ─── How it works section ─────────────────────────────────────────────────────

const STEPS = [
  {
    num: "01",
    title: "Connect your tools",
    desc: "Link GitHub, Slack, and Jira via OAuth in under a minute. Webhooks handle real-time events; a 15-minute poller fills in any gaps.",
  },
  {
    num: "02",
    title: "AI analyses activity",
    desc: "A LangGraph pipeline runs nightly. Six specialised agents collect signals, infer blockers, detect conflicts, and write narratives.",
  },
  {
    num: "03",
    title: "Receive your digest",
    desc: "A structured Slack message arrives each morning — developer summaries, blockers flagged, coordination risks highlighted.",
  },
];

function HowItWorksSection() {
  return (
    <section id="how-it-works" className="bg-black/30 py-28 px-6 border-t border-white/5">
      <div className="max-w-5xl mx-auto">
        <div className="text-center mb-16">
          <span className="text-xs text-gray-600 uppercase tracking-[0.2em] font-medium">How it works</span>
          <h2 className="text-3xl font-bold tracking-tight text-white mt-3">
            Up and running in minutes
          </h2>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-10">
          {STEPS.map((s) => (
            <div key={s.num}>
              <div
                className="font-instrument text-7xl leading-none mb-6"
                style={{ color: "rgba(255, 60, 0, 0.25)" }}
              >
                {s.num}
              </div>
              <h3 className="text-base font-semibold text-white mb-3">{s.title}</h3>
              <p className="text-sm text-gray-500 leading-relaxed">{s.desc}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

// ─── Footer ────────────────────────────────────────────────────────────────────

function Footer() {
  return (
    <footer className="border-t border-white/5 bg-slate-950 py-8 px-6">
      <div className="max-w-6xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-4">
        <div className="flex items-center gap-2.5">
          <div className="w-5 h-5 bg-white rounded flex items-center justify-center shrink-0">
            <svg className="w-3 h-3 text-gray-950" fill="currentColor" viewBox="0 0 24 24">
              <path d="M13 10V3L4 14h7v7l9-11h-7z" />
            </svg>
          </div>
          <span className="text-xs text-gray-600 font-medium tracking-tight">StandOut</span>
        </div>

        <div className="flex items-center gap-6">
          {/* GitHub */}
          <a href="https://github.com/VedantPandhare/Async-intelligence-layer" target="_blank" rel="noopener noreferrer"
            className="text-gray-600 hover:text-gray-300 transition-colors duration-200">
            <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
              <path d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.531 1.032 1.531 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z" />
            </svg>
          </a>
          {/* LinkedIn */}
          <a href="#" className="text-gray-600 hover:text-gray-300 transition-colors duration-200">
            <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
              <path d="M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433a2.062 2.062 0 01-2.063-2.065 2.064 2.064 0 112.063 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z" />
            </svg>
          </a>
        </div>

        <span className="text-xs text-gray-700">Built with LangGraph · FastAPI · Next.js</span>
      </div>
    </footer>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function LandingPage() {
  return (
    <div className="bg-slate-950 text-white">
      {/* ── Hero (full viewport) ───────────────────────────────────────────── */}
      <section className="relative min-h-screen flex flex-col items-center overflow-hidden">
        <div className="absolute inset-0 bg-slate-950" />
        <GradientBars />
        <Navbar />

        {/* Hero content */}
        <div className="relative z-10 flex flex-col items-center justify-center text-center min-h-screen w-full max-w-4xl mx-auto px-6 py-24">
          {/* Integration badge */}
          <div className="mb-8">
            <IntegrationBadge />
          </div>

          {/* Headline */}
          <h1 className="w-full leading-tight tracking-tight mb-7 px-2">
            <span
              className="block font-sans font-semibold text-white animate-fadeIn"
              style={{
                fontSize: "clamp(1.75rem, 5.5vw, 3.75rem)",
                animationDelay: "200ms",
              }}
            >
              Engineering intelligence,
            </span>
            <span
              className="block font-instrument italic text-gray-300 animate-fadeIn"
              style={{
                fontSize: "clamp(1.75rem, 5.5vw, 3.75rem)",
                animationDelay: "350ms",
              }}
            >
              delivered automatically.
            </span>
          </h1>

          {/* Subtext */}
          <div className="mb-10 px-4 space-y-1.5">
            <p
              className="text-gray-400 animate-fadeIn leading-relaxed"
              style={{ fontSize: "clamp(1rem, 2.5vw, 1.2rem)", animationDelay: "500ms" }}
            >
              Replace daily standups with AI-powered signal analysis.
            </p>
            <p
              className="text-gray-500 animate-fadeIn leading-relaxed"
              style={{ fontSize: "clamp(1rem, 2.5vw, 1.2rem)", animationDelay: "600ms" }}
            >
              Automated digests, blocker detection, and coordination insights.
            </p>
          </div>

          {/* CTAs */}
          <div
            className="flex flex-col sm:flex-row items-center gap-3 mb-10 animate-fadeIn"
            style={{ animationDelay: "750ms" }}
          >
            <Link
              href="/register"
              className="px-8 py-3.5 rounded-full bg-white hover:bg-gray-100 text-gray-950 font-medium text-sm transition-all duration-300 hover:scale-105 shadow-lg"
            >
              Get started for free
            </Link>
            <Link
              href="/login"
              className="px-8 py-3.5 rounded-full bg-gray-900/60 border border-white/10 text-white hover:bg-gray-800/60 text-sm transition-all duration-300 backdrop-blur-sm"
            >
              Sign in to workspace →
            </Link>
          </div>

          {/* Social links */}
          <div
            className="flex items-center gap-6 animate-fadeIn"
            style={{ animationDelay: "900ms" }}
          >
            <a
              href="https://github.com/VedantPandhare/Async-intelligence-layer"
              target="_blank"
              rel="noopener noreferrer"
              className="text-gray-600 hover:text-gray-300 transition-colors duration-200"
            >
              <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24">
                <path d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.531 1.032 1.531 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z" />
              </svg>
            </a>
            <a href="#" className="text-gray-600 hover:text-gray-300 transition-colors duration-200">
              <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24">
                <path d="M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433a2.062 2.062 0 01-2.063-2.065 2.064 2.064 0 112.063 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z" />
              </svg>
            </a>
          </div>
        </div>
      </section>

      {/* ── Features ──────────────────────────────────────────────────────── */}
      <FeaturesSection />

      {/* ── How it works ──────────────────────────────────────────────────── */}
      <HowItWorksSection />

      {/* ── Footer ────────────────────────────────────────────────────────── */}
      <Footer />
    </div>
  );
}
