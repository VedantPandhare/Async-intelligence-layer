"use client";

import { useEffect, useState } from "react";
import { apiFetch, type OrgSettings } from "@/lib/api";
import { getOrgId } from "@/lib/auth";
import Spinner from "@/components/Spinner";

const TIMEZONES = [
  "UTC", "America/New_York", "America/Chicago", "America/Denver",
  "America/Los_Angeles", "Europe/London", "Europe/Paris", "Europe/Berlin",
  "Asia/Kolkata", "Asia/Singapore", "Asia/Tokyo", "Australia/Sydney",
];

export default function SettingsPage() {
  const [settings, setSettings] = useState<OrgSettings | null>(null);
  const [form, setForm] = useState({ digest_time: "09:00", timezone: "UTC", slack_channel: "" });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState("");

  const orgId = getOrgId();

  useEffect(() => {
    if (!orgId) return;
    apiFetch<OrgSettings>(`/org/${orgId}/settings`)
      .then((data) => {
        setSettings(data);
        setForm({
          digest_time: data.digest_time,
          timezone: data.timezone,
          slack_channel: (data.settings?.slack_channel as string) || "",
        });
      })
      .catch((err) => setError(String(err)))
      .finally(() => setLoading(false));
  }, [orgId]);

  async function handleSave(e: React.FormEvent) {
    e.preventDefault();
    if (!orgId) return;
    setSaving(true);
    setSaved(false);
    setError("");
    try {
      await apiFetch(`/org/${orgId}/settings`, {
        method: "PATCH",
        body: JSON.stringify(form),
      });
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
    } catch (err) {
      setError(String(err));
    } finally {
      setSaving(false);
    }
  }

  if (loading) return (
    <div className="flex items-center justify-center h-64"><Spinner /></div>
  );

  return (
    <div className="max-w-2xl">
      <h1 className="mb-2">Settings</h1>
      {settings && (
        <p className="text-slate-400 text-sm mb-8">
          {settings.name} · <code className="text-slate-500 text-xs">{settings.id}</code>
        </p>
      )}

      <form onSubmit={handleSave} className="space-y-6">
        <div className="card space-y-5">
          <h2 className="text-base pb-3 border-b border-slate-800">Digest schedule</h2>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-medium text-slate-400 mb-1.5">
                Daily digest time
              </label>
              <input
                type="time"
                className="input"
                value={form.digest_time}
                onChange={(e) => setForm((f) => ({ ...f, digest_time: e.target.value }))}
              />
              <p className="text-xs text-slate-600 mt-1">In the org&apos;s timezone below</p>
            </div>

            <div>
              <label className="block text-xs font-medium text-slate-400 mb-1.5">
                Timezone
              </label>
              <select
                className="input"
                value={form.timezone}
                onChange={(e) => setForm((f) => ({ ...f, timezone: e.target.value }))}
              >
                {TIMEZONES.map((tz) => (
                  <option key={tz} value={tz}>{tz}</option>
                ))}
              </select>
            </div>
          </div>
        </div>

        <div className="card space-y-5">
          <h2 className="text-base pb-3 border-b border-slate-800">Delivery</h2>
          <div>
            <label className="block text-xs font-medium text-slate-400 mb-1.5">
              Slack channel
            </label>
            <input
              className="input"
              placeholder="#engineering-standup"
              value={form.slack_channel}
              onChange={(e) => setForm((f) => ({ ...f, slack_channel: e.target.value }))}
            />
            <p className="text-xs text-slate-600 mt-1">
              Channel where daily digests are posted. Falls back to email if Slack is not connected.
            </p>
          </div>
        </div>

        {error && (
          <div className="card border-red-800 bg-red-900/10">
            <p className="text-red-400 text-sm">{error}</p>
          </div>
        )}

        <div className="flex items-center gap-3">
          <button type="submit" className="btn-primary" disabled={saving}>
            {saving && <Spinner className="w-3.5 h-3.5" />}
            Save changes
          </button>
          {saved && (
            <span className="text-green-400 text-sm flex items-center gap-1.5">
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
              Saved
            </span>
          )}
        </div>
      </form>
    </div>
  );
}
