"use client";

import { useEffect, useState, Suspense } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import {
  apiFetch,
  getIntegrations,
  getGithubConnectUrl,
  getSlackConnectUrl,
  disconnectIntegration,
  importFromGitHub,
  type OrgSettings,
  type IntegrationStatus,
  type ImportResult,
} from "@/lib/api";
import { getOrgId } from "@/lib/auth";
import Spinner from "@/components/Spinner";

const TIMEZONES = [
  "UTC", "America/New_York", "America/Chicago", "America/Denver",
  "America/Los_Angeles", "Europe/London", "Europe/Paris", "Europe/Berlin",
  "Asia/Kolkata", "Asia/Singapore", "Asia/Tokyo", "Australia/Sydney",
];

// ─── Icons ────────────────────────────────────────────────────────────────────

function GithubIcon({ className = "w-4 h-4" }: { className?: string }) {
  return (
    <svg className={className} fill="currentColor" viewBox="0 0 24 24">
      <path d="M12 0C5.374 0 0 5.373 0 12c0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23A11.509 11.509 0 0 1 12 5.803c1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576C20.566 21.797 24 17.3 24 12c0-6.627-5.373-12-12-12z" />
    </svg>
  );
}

function SlackIcon({ className = "w-4 h-4" }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="currentColor">
      <path d="M5.042 15.165a2.528 2.528 0 0 1-2.52 2.523A2.528 2.528 0 0 1 0 15.165a2.527 2.527 0 0 1 2.522-2.52h2.52v2.52zm1.271 0a2.527 2.527 0 0 1 2.521-2.52 2.527 2.527 0 0 1 2.521 2.52v6.313A2.528 2.528 0 0 1 8.834 24a2.528 2.528 0 0 1-2.521-2.522v-6.313zM8.834 5.042a2.528 2.528 0 0 1-2.521-2.52A2.528 2.528 0 0 1 8.834 0a2.528 2.528 0 0 1 2.521 2.522v2.52H8.834zm0 1.271a2.528 2.528 0 0 1 2.521 2.521 2.528 2.528 0 0 1-2.521 2.521H2.522A2.528 2.528 0 0 1 0 8.834a2.528 2.528 0 0 1 2.522-2.521h6.312zm10.122 2.521a2.528 2.528 0 0 1 2.522-2.521A2.528 2.528 0 0 1 24 8.834a2.528 2.528 0 0 1-2.522 2.521h-2.522V8.834zm-1.268 0a2.528 2.528 0 0 1-2.523 2.521 2.527 2.527 0 0 1-2.52-2.521V2.522A2.527 2.527 0 0 1 15.165 0a2.528 2.528 0 0 1 2.523 2.522v6.312zm-2.523 10.122a2.528 2.528 0 0 1 2.523 2.522A2.528 2.528 0 0 1 15.165 24a2.527 2.527 0 0 1-2.52-2.522v-2.522h2.52zm0-1.268a2.527 2.527 0 0 1-2.52-2.523 2.526 2.526 0 0 1 2.52-2.52h6.313A2.527 2.527 0 0 1 24 15.165a2.528 2.528 0 0 1-2.522 2.523h-6.313z" />
    </svg>
  );
}

function CheckIcon() {
  return (
    <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 13l4 4L19 7" />
    </svg>
  );
}

// ─── Integration card ──────────────────────────────────────────────────────────

function IntegrationCard({
  icon,
  name,
  description,
  status,
  onConnect,
  onDisconnect,
  connecting,
  disconnecting,
  children,
}: {
  icon: React.ReactNode;
  name: string;
  description: string;
  status: IntegrationStatus;
  onConnect: () => void;
  onDisconnect: () => void;
  connecting: boolean;
  disconnecting: boolean;
  children?: React.ReactNode;
}) {
  return (
    <div className="card space-y-4">
      <div className="flex items-start gap-4">
        <div
          className={`w-9 h-9 rounded-lg flex items-center justify-center shrink-0 ${
            status.connected ? "bg-green-950/50" : "bg-slate-800"
          }`}
        >
          <span className={status.connected ? "text-green-400" : "text-slate-400"}>{icon}</span>
        </div>

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2.5">
            <h3 className="text-sm font-semibold text-white">{name}</h3>
            {status.connected ? (
              <span className="badge-green text-xs">Connected</span>
            ) : (
              <span className="badge-slate text-xs">Not connected</span>
            )}
          </div>
          {status.connected && status.metadata?.workspace_name && (
            <p className="text-xs text-slate-500 mt-0.5">{status.metadata.workspace_name}</p>
          )}
          {status.connected && status.metadata?.github_username && (
            <p className="text-xs text-slate-500 mt-0.5">@{status.metadata.github_username}</p>
          )}
          {!status.connected && (
            <p className="text-xs text-slate-600 mt-0.5">{description}</p>
          )}
        </div>

        <div className="shrink-0">
          {status.connected ? (
            <button
              onClick={onDisconnect}
              disabled={disconnecting}
              className="btn-danger text-xs px-3 py-1.5"
            >
              {disconnecting ? <Spinner className="w-3 h-3" /> : "Disconnect"}
            </button>
          ) : (
            <button
              onClick={onConnect}
              disabled={connecting}
              className="btn-secondary text-xs px-3 py-1.5"
            >
              {connecting ? <Spinner className="w-3 h-3" /> : "Connect"}
            </button>
          )}
        </div>
      </div>

      {status.connected && children && (
        <div className="border-t border-slate-800 pt-4 space-y-4">{children}</div>
      )}
    </div>
  );
}

// ─── Main page ────────────────────────────────────────────────────────────────

function SettingsContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const orgId = getOrgId();

  const [orgSettings, setOrgSettings] = useState<OrgSettings | null>(null);
  const [github, setGithub] = useState<IntegrationStatus>({ connected: false });
  const [slack, setSlack] = useState<IntegrationStatus>({ connected: false });
  const [loading, setLoading] = useState(true);
  const [toast, setToast] = useState("");

  // Schedule form
  const [scheduleForm, setScheduleForm] = useState({ digest_time: "09:00", timezone: "UTC" });
  const [savingSchedule, setSavingSchedule] = useState(false);

  // GitHub config form
  const [ghForm, setGhForm] = useState({ github_org: "", github_repos: "" });
  const [savingGh, setSavingGh] = useState(false);
  const [importingDevs, setImportingDevs] = useState(false);
  const [importResult, setImportResult] = useState<ImportResult | null>(null);
  const [importError, setImportError] = useState("");

  // Computed — true whenever GitHub is connected but the stored token lacks read:org
  const needsReconnect = github.connected && !(github.metadata?.scope ?? "").includes("read:org");

  // Slack config form
  const [slackForm, setSlackForm] = useState({ slack_channel: "", slack_read_channels: "" });
  const [savingSlack, setSavingSlack] = useState(false);

  // Connect / disconnect states
  const [connectingGh, setConnectingGh] = useState(false);
  const [connectingSlack, setConnectingSlack] = useState(false);
  const [disconnecting, setDisconnecting] = useState("");

  function showToast(msg: string) {
    setToast(msg);
    setTimeout(() => setToast(""), 3500);
  }

  async function loadData() {
    if (!orgId) return;
    try {
      const [settings, integrations] = await Promise.all([
        apiFetch<OrgSettings>(`/org/${orgId}/settings`),
        getIntegrations(orgId),
      ]);
      setOrgSettings(settings);
      setGithub(integrations.github);
      setSlack(integrations.slack);

      setScheduleForm({
        digest_time: settings.digest_time,
        timezone: settings.timezone,
      });
      setGhForm({
        github_org: (settings.settings?.github_org as string) || "",
        github_repos: ((settings.settings?.github_repos as string[]) || []).join(", "),
      });
      setSlackForm({
        slack_channel: (settings.settings?.slack_channel as string) || "",
        slack_read_channels: ((settings.settings?.slack_read_channels as string[]) || []).join(", "),
      });
    } catch { /* handled by loading state */ }
    finally { setLoading(false); }
  }

  useEffect(() => {
    if (!orgId) { router.push("/login"); return; }
    loadData();
  }, [orgId]);  // eslint-disable-line react-hooks/exhaustive-deps

  // Handle OAuth callback redirect back to settings
  useEffect(() => {
    const connected = searchParams.get("connected");
    if (connected) {
      showToast(`${connected.charAt(0).toUpperCase() + connected.slice(1)} connected successfully`);
      loadData();
      router.replace("/dashboard/settings");
    }
  }, [searchParams]);  // eslint-disable-line react-hooks/exhaustive-deps

  async function saveSchedule(e: React.FormEvent) {
    e.preventDefault();
    if (!orgId) return;
    setSavingSchedule(true);
    try {
      await apiFetch(`/org/${orgId}/settings`, { method: "PATCH", body: JSON.stringify(scheduleForm) });
      showToast("Schedule saved");
    } catch (err) { showToast(`Error: ${err instanceof Error ? err.message : String(err)}`); }
    finally { setSavingSchedule(false); }
  }

  async function saveGitHub(e: React.FormEvent) {
    e.preventDefault();
    if (!orgId) return;
    setSavingGh(true);
    try {
      const repos = ghForm.github_repos.split(",").map((r) => r.trim()).filter(Boolean);
      await apiFetch(`/org/${orgId}/settings`, {
        method: "PATCH",
        body: JSON.stringify({ github_org: ghForm.github_org, github_repos: repos }),
      });
      showToast("GitHub config saved");
    } catch (err) { showToast(`Error: ${err instanceof Error ? err.message : String(err)}`); }
    finally { setSavingGh(false); }
  }

  async function saveSlack(e: React.FormEvent) {
    e.preventDefault();
    if (!orgId) return;
    setSavingSlack(true);
    try {
      const channels = slackForm.slack_read_channels.split(",").map((c) => c.trim()).filter(Boolean);
      await apiFetch(`/org/${orgId}/settings`, {
        method: "PATCH",
        body: JSON.stringify({ slack_channel: slackForm.slack_channel, slack_read_channels: channels }),
      });
      showToast("Slack config saved");
    } catch (err) { showToast(`Error: ${err instanceof Error ? err.message : String(err)}`); }
    finally { setSavingSlack(false); }
  }

  async function handleImportDevs() {
    if (!orgId) return;
    setImportingDevs(true);
    setImportResult(null);
    setImportError("");
    try {
      const result = await importFromGitHub(orgId);
      setImportResult(result);
      showToast(`Imported ${result.imported} developer${result.imported !== 1 ? "s" : ""}`);
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      if (!msg.includes("MISSING_READ_ORG_SCOPE")) {
        setImportError(msg);
      }
      // If MISSING_READ_ORG_SCOPE: needsReconnect is computed from github.metadata.scope automatically
    } finally { setImportingDevs(false); }
  }

  async function handleConnect(provider: "github" | "slack") {
    if (!orgId) return;
    if (provider === "github") {
      setConnectingGh(true);
      try {
        const url = await getGithubConnectUrl(orgId, "/dashboard/settings");
        window.location.href = url;
      } catch { setConnectingGh(false); }
    } else {
      setConnectingSlack(true);
      try {
        const url = await getSlackConnectUrl(orgId, "/dashboard/settings");
        window.location.href = url;
      } catch { setConnectingSlack(false); }
    }
  }

  async function handleDisconnect(provider: string) {
    if (!orgId) return;
    setDisconnecting(provider);
    try {
      await disconnectIntegration(orgId, provider);
      await loadData();
      showToast(`${provider} disconnected`);
    } catch (err) {
      showToast(`Error: ${err instanceof Error ? err.message : String(err)}`);
    } finally { setDisconnecting(""); }
  }

  if (loading) return (
    <div className="flex items-center justify-center h-64"><Spinner /></div>
  );

  return (
    <div className="max-w-2xl space-y-10">
      {/* Toast */}
      {toast && (
        <div className="fixed top-4 right-4 z-50 bg-slate-800 border border-slate-700 text-slate-200 text-sm rounded-lg px-4 py-2.5 shadow-xl flex items-center gap-2 animate-fadeIn">
          <span className="text-green-400"><CheckIcon /></span>
          {toast}
        </div>
      )}

      <div>
        <h1 className="page-title">Settings</h1>
        {orgSettings && (
          <p className="page-subtitle">
            {orgSettings.name}
            <span className="mx-2 text-slate-700">·</span>
            <code className="text-xs text-slate-700 font-mono">{orgSettings.id}</code>
          </p>
        )}
      </div>

      {/* ── Integrations ── */}
      <section className="space-y-3">
        <div className="pb-1">
          <h2 className="text-sm font-semibold text-white">Integrations</h2>
          <p className="text-xs text-slate-600 mt-0.5">Connect your tools so the poller knows where to look</p>
        </div>

        {/* GitHub */}
        <IntegrationCard
          icon={<GithubIcon />}
          name="GitHub"
          description="Enables commit, PR, and CI activity tracking"
          status={github}
          onConnect={() => handleConnect("github")}
          onDisconnect={() => handleDisconnect("github")}
          connecting={connectingGh}
          disconnecting={disconnecting === "github"}
        >
          <form onSubmit={saveGitHub} className="space-y-4">
            {/* Reconnect warning — shown when token lacks read:org */}
            {needsReconnect && (
              <div className="bg-orange-950/30 border border-orange-900/50 rounded-lg p-3.5 flex items-start gap-3">
                <svg className="w-4 h-4 text-orange-400 mt-0.5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" />
                </svg>
                <div className="flex-1 min-w-0">
                  <p className="text-sm text-orange-300 font-medium">GitHub reconnect needed</p>
                  <p className="text-xs text-orange-400/80 mt-0.5">
                    Your GitHub token is missing <code className="font-mono">read:org</code> permission (it was connected before this scope was added).
                    Disconnect and reconnect to fix it.
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => handleConnect("github")}
                  disabled={connectingGh}
                  className="btn-secondary text-xs px-3 py-1.5 shrink-0"
                >
                  {connectingGh ? <Spinner className="w-3 h-3" /> : "Reconnect"}
                </button>
              </div>
            )}

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="label">GitHub organisation</label>
                <input
                  className="input"
                  placeholder="Club-Syndicate"
                  value={ghForm.github_org}
                  onChange={(e) => {
                    setGhForm((f) => ({ ...f, github_org: e.target.value }));
                    setImportResult(null);
                    setImportError("");
                  }}
                  list="gh-orgs-list"
                />
                {/* datalist provides autocomplete from OAuth metadata without hiding the input */}
                <datalist id="gh-orgs-list">
                  {(github.metadata?.github_orgs ?? []).map((o) => (
                    <option key={o} value={o} />
                  ))}
                </datalist>
                <p className="text-xs text-slate-700 mt-1">
                  Org slug from github.com/your-org
                </p>
              </div>
              <div>
                <label className="label">Repos to watch</label>
                <input
                  className="input"
                  placeholder="api, frontend (empty = all)"
                  value={ghForm.github_repos}
                  onChange={(e) => setGhForm((f) => ({ ...f, github_repos: e.target.value }))}
                />
                <p className="text-xs text-slate-700 mt-1">
                  Comma-separated. Leave empty to watch all.
                </p>
              </div>
            </div>

            <div className="flex items-center gap-3">
              <button type="submit" className="btn-secondary text-xs" disabled={savingGh}>
                {savingGh && <Spinner className="w-3 h-3" />}
                Save config
              </button>

              <button
                type="button"
                onClick={handleImportDevs}
                disabled={importingDevs || !ghForm.github_org}
                className="btn-ghost text-xs"
              >
                {importingDevs && <Spinner className="w-3 h-3" />}
                {importingDevs ? "Importing…" : "Import teammates"}
              </button>
            </div>

            {importError && (
              <p className="text-xs text-red-400">{importError}</p>
            )}

            {importResult && importResult.imported === 0 && importResult.skipped === 0 && (
              <div className="bg-slate-800/60 border border-slate-700 rounded-lg p-3 text-xs text-slate-400 space-y-1.5">
                <p className="font-medium text-slate-300">GitHub returned 0 members — possible causes:</p>
                <ul className="space-y-1 list-disc list-inside text-slate-500">
                  <li>The org has restricted third-party app access (most common)</li>
                  <li>The org name is wrong or doesn&apos;t exist</li>
                  <li>All members have private profiles</li>
                </ul>
                <p className="pt-1">To grant access, visit the org&apos;s OAuth policy page:</p>
                <a
                  href={`https://github.com/organizations/${ghForm.github_org}/settings/oauth_application_policy`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-blue-400 hover:text-blue-300 underline break-all"
                >
                  github.com/organizations/{ghForm.github_org}/settings/oauth_application_policy
                </a>
                <p className="text-slate-500 pt-1">After granting access, click &quot;Import teammates&quot; again.</p>
              </div>
            )}
            {importResult && importResult.skipped > 0 && importResult.imported === 0 && (
              <p className="text-xs text-slate-500">
                {importResult.skipped} developer{importResult.skipped !== 1 ? "s" : ""} already in your workspace
              </p>
            )}

            {importResult && importResult.imported > 0 && (
              <p className="text-xs text-green-400">
                ✓ Imported {importResult.imported} developer{importResult.imported !== 1 ? "s" : ""}
                {importResult.skipped > 0 && `, ${importResult.skipped} already existed`}
              </p>
            )}
          </form>
        </IntegrationCard>

        {/* Slack */}
        <IntegrationCard
          icon={<SlackIcon />}
          name="Slack"
          description="Enables digest delivery and conversation context"
          status={slack}
          onConnect={() => handleConnect("slack")}
          onDisconnect={() => handleDisconnect("slack")}
          connecting={connectingSlack}
          disconnecting={disconnecting === "slack"}
        >
          <form onSubmit={saveSlack} className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="label">Post digests to channel</label>
                <input
                  className="input"
                  placeholder="#engineering"
                  value={slackForm.slack_channel}
                  onChange={(e) => setSlackForm((f) => ({ ...f, slack_channel: e.target.value }))}
                />
                <p className="text-xs text-slate-700 mt-1">Where daily digests are delivered</p>
              </div>
              <div>
                <label className="label">Read from channels</label>
                <input
                  className="input"
                  placeholder="engineering, dev-updates"
                  value={slackForm.slack_read_channels}
                  onChange={(e) => setSlackForm((f) => ({ ...f, slack_read_channels: e.target.value }))}
                />
                <p className="text-xs text-slate-700 mt-1">
                  Comma-separated. Used for blocker detection.
                </p>
              </div>
            </div>

            {slack.metadata?.channels && slack.metadata.channels.length > 0 && (
              <div>
                <p className="text-xs text-slate-600 mb-1.5">Available channels in this workspace:</p>
                <div className="flex flex-wrap gap-1.5">
                  {slack.metadata.channels.slice(0, 12).map((ch) => (
                    <button
                      key={ch.id}
                      type="button"
                      onClick={() => {
                        const current = slackForm.slack_read_channels;
                        const names = current.split(",").map((c) => c.trim()).filter(Boolean);
                        if (!names.includes(ch.name)) {
                          setSlackForm((f) => ({
                            ...f,
                            slack_read_channels: [...names, ch.name].join(", "),
                          }));
                        }
                      }}
                      className="text-xs bg-slate-800 hover:bg-slate-700 text-slate-400 hover:text-slate-200 px-2 py-0.5 rounded transition-colors"
                    >
                      #{ch.name}
                    </button>
                  ))}
                </div>
              </div>
            )}

            <button type="submit" className="btn-secondary text-xs" disabled={savingSlack}>
              {savingSlack && <Spinner className="w-3 h-3" />}
              Save Slack config
            </button>
          </form>
        </IntegrationCard>
      </section>

      {/* ── Digest schedule ── */}
      <section>
        <form onSubmit={saveSchedule} className="card space-y-5">
          <div className="pb-3 border-b border-slate-800">
            <h2 className="text-sm font-semibold text-white">Digest schedule</h2>
            <p className="text-xs text-slate-600 mt-0.5">When to generate and deliver the daily digest</p>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="label">Daily digest time</label>
              <input
                type="time"
                className="input"
                value={scheduleForm.digest_time}
                onChange={(e) => setScheduleForm((f) => ({ ...f, digest_time: e.target.value }))}
              />
            </div>
            <div>
              <label className="label">Timezone</label>
              <select
                className="input"
                value={scheduleForm.timezone}
                onChange={(e) => setScheduleForm((f) => ({ ...f, timezone: e.target.value }))}
              >
                {TIMEZONES.map((tz) => (
                  <option key={tz} value={tz}>{tz}</option>
                ))}
              </select>
            </div>
          </div>

          <button type="submit" className="btn-primary text-sm" disabled={savingSchedule}>
            {savingSchedule && <Spinner className="w-3.5 h-3.5 border-slate-400 border-t-slate-950" />}
            Save schedule
          </button>
        </form>
      </section>
    </div>
  );
}

export default function SettingsPage() {
  return (
    <Suspense fallback={<div className="flex items-center justify-center h-64"><Spinner /></div>}>
      <SettingsContent />
    </Suspense>
  );
}
