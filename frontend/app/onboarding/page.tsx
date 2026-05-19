"use client";

import { useEffect, useState, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import {
  apiFetch,
  getIntegrations,
  getGithubConnectUrl,
  getSlackConnectUrl,
  importFromGitHub,
  type IntegrationStatus,
  type ImportResult,
} from "@/lib/api";
import { getOrgId as authGetOrgId } from "@/lib/auth";
import Spinner from "@/components/Spinner";

// ─── Step definitions ─────────────────────────────────────────────────────────

const STEPS = [
  { id: 1, label: "Connect GitHub" },
  { id: 2, label: "Import team" },
  { id: 3, label: "Connect Slack" },
];

// ─── Icons ────────────────────────────────────────────────────────────────────

function GithubIcon({ className = "w-5 h-5" }: { className?: string }) {
  return (
    <svg className={className} fill="currentColor" viewBox="0 0 24 24">
      <path d="M12 0C5.374 0 0 5.373 0 12c0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23A11.509 11.509 0 0 1 12 5.803c1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576C20.566 21.797 24 17.3 24 12c0-6.627-5.373-12-12-12z" />
    </svg>
  );
}

function SlackIcon({ className = "w-5 h-5" }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="currentColor">
      <path d="M5.042 15.165a2.528 2.528 0 0 1-2.52 2.523A2.528 2.528 0 0 1 0 15.165a2.527 2.527 0 0 1 2.522-2.52h2.52v2.52zm1.271 0a2.527 2.527 0 0 1 2.521-2.52 2.527 2.527 0 0 1 2.521 2.52v6.313A2.528 2.528 0 0 1 8.834 24a2.528 2.528 0 0 1-2.521-2.522v-6.313zM8.834 5.042a2.528 2.528 0 0 1-2.521-2.52A2.528 2.528 0 0 1 8.834 0a2.528 2.528 0 0 1 2.521 2.522v2.52H8.834zm0 1.271a2.528 2.528 0 0 1 2.521 2.521 2.528 2.528 0 0 1-2.521 2.521H2.522A2.528 2.528 0 0 1 0 8.834a2.528 2.528 0 0 1 2.522-2.521h6.312zm10.122 2.521a2.528 2.528 0 0 1 2.522-2.521A2.528 2.528 0 0 1 24 8.834a2.528 2.528 0 0 1-2.522 2.521h-2.522V8.834zm-1.268 0a2.528 2.528 0 0 1-2.523 2.521 2.527 2.527 0 0 1-2.52-2.521V2.522A2.527 2.527 0 0 1 15.165 0a2.528 2.528 0 0 1 2.523 2.522v6.312zm-2.523 10.122a2.528 2.528 0 0 1 2.523 2.522A2.528 2.528 0 0 1 15.165 24a2.527 2.527 0 0 1-2.52-2.522v-2.522h2.52zm0-1.268a2.527 2.527 0 0 1-2.52-2.523 2.526 2.526 0 0 1 2.52-2.52h6.313A2.527 2.527 0 0 1 24 15.165a2.528 2.528 0 0 1-2.522 2.523h-6.313z" />
    </svg>
  );
}

function CheckIcon() {
  return (
    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 13l4 4L19 7" />
    </svg>
  );
}

// ─── Main component (wrapped for Suspense) ────────────────────────────────────

function OnboardingContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const orgId = authGetOrgId();

  const [step, setStep] = useState(1);
  const [github, setGithub] = useState<IntegrationStatus>({ connected: false });
  const [slack, setSlack] = useState<IntegrationStatus>({ connected: false });
  const [githubOrgs, setGithubOrgs] = useState<string[]>([]);
  const [selectedOrg, setSelectedOrg] = useState("");
  const [importing, setImporting] = useState(false);
  const [importResult, setImportResult] = useState<ImportResult | null>(null);
  const [importError, setImportError] = useState("");
  const [connecting, setConnecting] = useState<"github" | "slack" | null>(null);

  // Fetch current integration status on mount
  useEffect(() => {
    if (!orgId) { router.push("/login"); return; }
    getIntegrations(orgId).then((data) => {
      setGithub(data.github);
      setSlack(data.slack);
      if (data.github.connected) {
        const orgs = data.github.metadata?.github_orgs ?? [];
        setGithubOrgs(orgs);
        if (orgs.length === 1) setSelectedOrg(orgs[0]);
      }
    }).catch(() => {});
  }, [orgId, router]);

  // Handle OAuth callback redirects from backend
  useEffect(() => {
    const connected = searchParams.get("connected");
    const error = searchParams.get("error");

    if (connected === "github") {
      // Re-fetch integrations to get fresh status + github_orgs
      if (orgId) {
        getIntegrations(orgId).then((data) => {
          setGithub(data.github);
          const orgs = data.github.metadata?.github_orgs ?? [];
          setGithubOrgs(orgs);
          if (orgs.length === 1) setSelectedOrg(orgs[0]);
        }).catch(() => {});
      }
      setStep(2);
      // Clean URL
      router.replace("/onboarding");
    } else if (connected === "slack") {
      if (orgId) {
        getIntegrations(orgId).then((data) => setSlack(data.slack)).catch(() => {});
      }
      // Stay on step 3
      router.replace("/onboarding");
    } else if (error) {
      router.replace("/onboarding");
    }
  }, [searchParams, orgId, router]);

  // Also advance step if already connected on load
  useEffect(() => {
    if (github.connected && step === 1) setStep(2);
  }, [github.connected]);  // eslint-disable-line react-hooks/exhaustive-deps

  async function connectGitHub() {
    if (!orgId) return;
    setConnecting("github");
    try {
      const url = await getGithubConnectUrl(orgId, "/onboarding");
      window.location.href = url;
    } catch {
      setConnecting(null);
    }
  }

  async function connectSlack() {
    if (!orgId) return;
    setConnecting("slack");
    try {
      const url = await getSlackConnectUrl(orgId, "/onboarding");
      window.location.href = url;
    } catch {
      setConnecting(null);
    }
  }

  async function handleImport() {
    if (!orgId) return;
    setImporting(true);
    setImportError("");

    // Save selected org to settings first
    if (selectedOrg) {
      try {
        await apiFetch(`/org/${orgId}/settings`, {
          method: "PATCH",
          body: JSON.stringify({ github_org: selectedOrg }),
        });
      } catch { /* non-fatal */ }
    }

    try {
      const result = await importFromGitHub(orgId);
      setImportResult(result);
    } catch (err: unknown) {
      setImportError(err instanceof Error ? err.message : "Import failed");
    } finally {
      setImporting(false);
    }
  }

  const progressPct = ((step - 1) / (STEPS.length - 1)) * 100;

  return (
    <div className="min-h-screen bg-slate-950 flex flex-col">
      {/* Header */}
      <header className="h-14 border-b border-white/5 flex items-center justify-between px-6">
        <Link href="/" className="flex items-center gap-2.5">
          <div className="w-6 h-6 bg-white rounded flex items-center justify-center shrink-0">
            <svg className="w-3.5 h-3.5 text-slate-950" fill="currentColor" viewBox="0 0 24 24">
              <path d="M13 10V3L4 14h7v7l9-11h-7z" />
            </svg>
          </div>
          <span className="text-sm font-semibold tracking-tight">StandOut</span>
        </Link>
        <button
          onClick={() => router.push("/dashboard")}
          className="text-xs text-slate-500 hover:text-slate-300 transition-colors"
        >
          Skip setup →
        </button>
      </header>

      <div className="flex-1 flex items-start justify-center px-4 py-12">
        <div className="w-full max-w-lg">
          {/* Progress */}
          <div className="mb-10">
            <div className="flex items-center justify-between mb-3">
              {STEPS.map((s, i) => (
                <div key={s.id} className="flex items-center gap-2">
                  <div
                    className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-semibold transition-all ${
                      step > s.id
                        ? "bg-green-500 text-white"
                        : step === s.id
                        ? "bg-white text-slate-950"
                        : "bg-slate-800 text-slate-500"
                    }`}
                  >
                    {step > s.id ? <CheckIcon /> : s.id}
                  </div>
                  <span
                    className={`text-xs font-medium hidden sm:block ${
                      step === s.id ? "text-white" : "text-slate-600"
                    }`}
                  >
                    {s.label}
                  </span>
                  {i < STEPS.length - 1 && (
                    <div className="flex-1 h-px bg-slate-800 mx-3 hidden sm:block" style={{ width: 40 }}>
                      <div
                        className="h-full bg-green-500 transition-all duration-500"
                        style={{ width: step > s.id ? "100%" : "0%" }}
                      />
                    </div>
                  )}
                </div>
              ))}
            </div>
            {/* Mobile progress bar */}
            <div className="sm:hidden h-1 bg-slate-800 rounded-full mt-3">
              <div
                className="h-full bg-white rounded-full transition-all duration-500"
                style={{ width: `${progressPct}%` }}
              />
            </div>
          </div>

          {/* ── Step 1: Connect GitHub ── */}
          {step === 1 && (
            <div className="card space-y-6 animate-fadeIn">
              <div className="flex items-start gap-4">
                <div className="w-10 h-10 bg-slate-800 rounded-lg flex items-center justify-center shrink-0">
                  <GithubIcon className="w-5 h-5 text-white" />
                </div>
                <div>
                  <h2 className="text-base font-semibold text-white">Connect GitHub</h2>
                  <p className="text-sm text-slate-500 mt-1">
                    StandOut needs read access to your org's commits, pull requests, and CI runs.
                    We never write to your repositories.
                  </p>
                </div>
              </div>

              <div className="bg-slate-800/50 rounded-lg p-4 space-y-2">
                {[
                  "Read commits & pull requests",
                  "Read CI/CD run status",
                  "List org members (for import)",
                ].map((p) => (
                  <div key={p} className="flex items-center gap-2.5 text-sm text-slate-400">
                    <div className="w-1.5 h-1.5 rounded-full bg-slate-600" />
                    {p}
                  </div>
                ))}
              </div>

              <button
                onClick={connectGitHub}
                disabled={connecting === "github"}
                className="btn-primary w-full justify-center py-2.5 gap-2.5"
              >
                {connecting === "github" ? (
                  <Spinner className="w-4 h-4 border-slate-400 border-t-slate-950" />
                ) : (
                  <GithubIcon className="w-4 h-4" />
                )}
                {connecting === "github" ? "Redirecting to GitHub…" : "Connect GitHub"}
              </button>
            </div>
          )}

          {/* ── Step 2: Import team ── */}
          {step === 2 && (
            <div className="space-y-4 animate-fadeIn">
              {/* GitHub connected badge */}
              <div className="card flex items-center gap-3 py-3.5">
                <div className="w-8 h-8 bg-green-950/60 rounded-lg flex items-center justify-center">
                  <GithubIcon className="w-4 h-4 text-green-400" />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-white">GitHub connected</p>
                  {github.metadata?.github_username && (
                    <p className="text-xs text-slate-500">as @{github.metadata.github_username}</p>
                  )}
                </div>
                <span className="badge-green text-xs">Connected</span>
              </div>

              {/* Import card */}
              <div className="card space-y-5">
                <div>
                  <h2 className="text-base font-semibold text-white">Import your team</h2>
                  <p className="text-sm text-slate-500 mt-1">
                    Select your GitHub organisation to pull in all members as tracked developers.
                  </p>
                </div>

                {githubOrgs.length > 0 ? (
                  <div>
                    <label className="label">GitHub organisation</label>
                    <select
                      className="input"
                      value={selectedOrg}
                      onChange={(e) => setSelectedOrg(e.target.value)}
                    >
                      <option value="">Select an organisation…</option>
                      {githubOrgs.map((o) => (
                        <option key={o} value={o}>{o}</option>
                      ))}
                    </select>
                    <p className="text-xs text-slate-600 mt-1.5">
                      These are orgs accessible to the connected GitHub account.
                    </p>
                  </div>
                ) : (
                  <div>
                    <label className="label">GitHub organisation or username</label>
                    <input
                      className="input"
                      placeholder="e.g. acme-inc"
                      value={selectedOrg}
                      onChange={(e) => setSelectedOrg(e.target.value)}
                    />
                    <p className="text-xs text-slate-600 mt-1.5">
                      Enter your GitHub org slug (the part after github.com/).
                    </p>
                  </div>
                )}

                {importResult ? (
                  <div className="bg-green-950/30 border border-green-900/50 rounded-lg p-4 space-y-2">
                    <p className="text-sm font-medium text-green-400">
                      ✓ Imported {importResult.imported} developer{importResult.imported !== 1 ? "s" : ""}
                      {importResult.skipped > 0 && `, ${importResult.skipped} already existed`}
                    </p>
                    {importResult.developers.slice(0, 5).map((d) => (
                      <p key={d.github_username} className="text-xs text-slate-500">
                        @{d.github_username} {d.name !== d.github_username && `· ${d.name}`}
                      </p>
                    ))}
                    {importResult.developers.length > 5 && (
                      <p className="text-xs text-slate-600">
                        +{importResult.developers.length - 5} more
                      </p>
                    )}
                  </div>
                ) : (
                  <>
                    {importError && (
                      <p className="text-sm text-red-400 bg-red-950/40 border border-red-900/50 rounded-lg px-3 py-2.5">
                        {importError}
                      </p>
                    )}
                    <button
                      onClick={handleImport}
                      disabled={importing || !selectedOrg}
                      className="btn-primary w-full justify-center py-2.5"
                    >
                      {importing && <Spinner className="w-4 h-4 border-slate-400 border-t-slate-950" />}
                      {importing ? "Importing…" : "Import teammates from GitHub"}
                    </button>
                  </>
                )}
              </div>

              <div className="flex gap-3">
                <button
                  onClick={() => setStep(3)}
                  className="btn-primary flex-1 justify-center py-2.5"
                >
                  Continue →
                </button>
              </div>
            </div>
          )}

          {/* ── Step 3: Connect Slack ── */}
          {step === 3 && (
            <div className="space-y-4 animate-fadeIn">
              {/* Connected summary */}
              <div className="card flex items-center gap-3 py-3.5">
                <div className="w-8 h-8 bg-green-950/60 rounded-lg flex items-center justify-center">
                  <GithubIcon className="w-4 h-4 text-green-400" />
                </div>
                <div className="flex-1">
                  <p className="text-sm font-medium text-white">GitHub connected</p>
                </div>
                <span className="badge-green">Connected</span>
              </div>

              {slack.connected ? (
                <div className="card flex items-center gap-3 py-3.5">
                  <div className="w-8 h-8 bg-green-950/60 rounded-lg flex items-center justify-center">
                    <SlackIcon className="w-4 h-4 text-green-400" />
                  </div>
                  <div className="flex-1">
                    <p className="text-sm font-medium text-white">Slack connected</p>
                    {slack.metadata?.workspace_name && (
                      <p className="text-xs text-slate-500">{slack.metadata.workspace_name}</p>
                    )}
                  </div>
                  <span className="badge-green">Connected</span>
                </div>
              ) : (
                <div className="card space-y-5">
                  <div className="flex items-start gap-4">
                    <div className="w-10 h-10 bg-slate-800 rounded-lg flex items-center justify-center shrink-0">
                      <SlackIcon className="w-5 h-5 text-white" />
                    </div>
                    <div>
                      <h2 className="text-base font-semibold text-white">Connect Slack</h2>
                      <p className="text-sm text-slate-500 mt-1">
                        Optional — lets StandOut deliver digests to your team channel and read
                        conversation context to detect blockers.
                      </p>
                    </div>
                  </div>

                  <div className="bg-slate-800/50 rounded-lg p-4 space-y-2">
                    {[
                      "Read specified public channels",
                      "Post digests to your team channel",
                      "Look up user profiles",
                    ].map((p) => (
                      <div key={p} className="flex items-center gap-2.5 text-sm text-slate-400">
                        <div className="w-1.5 h-1.5 rounded-full bg-slate-600" />
                        {p}
                      </div>
                    ))}
                  </div>

                  <button
                    onClick={connectSlack}
                    disabled={connecting === "slack"}
                    className="btn-secondary w-full justify-center py-2.5 gap-2.5"
                  >
                    {connecting === "slack" ? (
                      <Spinner className="w-4 h-4" />
                    ) : (
                      <SlackIcon className="w-4 h-4" />
                    )}
                    {connecting === "slack" ? "Redirecting to Slack…" : "Add to Slack"}
                  </button>
                </div>
              )}

              <button
                onClick={() => router.push("/dashboard")}
                className="btn-primary w-full justify-center py-2.5 mt-2"
              >
                Go to dashboard →
              </button>
              {!slack.connected && (
                <p className="text-center text-xs text-slate-600">
                  You can connect Slack later in Settings
                </p>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default function OnboardingPage() {
  return (
    <Suspense fallback={
      <div className="min-h-screen bg-slate-950 flex items-center justify-center">
        <Spinner className="w-6 h-6" />
      </div>
    }>
      <OnboardingContent />
    </Suspense>
  );
}
