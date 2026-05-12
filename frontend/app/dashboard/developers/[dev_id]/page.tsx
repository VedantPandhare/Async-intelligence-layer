"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { apiFetch, type Developer, type TimelineEvent } from "@/lib/api";
import { getOrgId } from "@/lib/auth";
import Spinner from "@/components/Spinner";

const SOURCE_BADGE: Record<string, string> = {
  github: "badge-slate",
  slack:  "badge-green",
  jira:   "badge-blue",
};

const EVENT_ICON_PATH: Record<string, string> = {
  commit:        "M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4",
  pull_request:  "M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4",
  ci_run:        "M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z",
  slack_message: "M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z",
  jira_issue:    "M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2",
};

const TIME_WINDOWS = [
  { h: 8,   label: "8h" },
  { h: 24,  label: "24h" },
  { h: 48,  label: "2d" },
  { h: 168, label: "7d" },
];

export default function DeveloperTimelinePage() {
  const params = useParams();
  const devId = params.dev_id as string;
  const orgId = getOrgId();

  const [dev, setDev] = useState<Developer | null>(null);
  const [events, setEvents] = useState<TimelineEvent[]>([]);
  const [hours, setHours] = useState(24);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  async function load(h = hours) {
    if (!orgId || !devId) return;
    setLoading(true);
    setError("");
    try {
      const [devData, eventsData] = await Promise.all([
        apiFetch<Developer>(`/developers/${orgId}/${devId}`),
        apiFetch<TimelineEvent[]>(`/developers/${orgId}/${devId}/timeline?hours=${h}`),
      ]);
      setDev(devData);
      setEvents(eventsData);
    } catch (err) {
      setError(String(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, [orgId, devId]);

  if (loading) return (
    <div className="flex items-center justify-center h-64"><Spinner /></div>
  );

  if (error) return (
    <div className="error-card"><p className="text-red-400 text-sm">{error}</p></div>
  );

  return (
    <div className="max-w-3xl">
      {/* Back + profile */}
      <div className="flex items-center gap-3 mb-8">
        <Link
          href="/dashboard/developers"
          className="text-slate-600 hover:text-slate-300 transition-colors"
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M15 19l-7-7 7-7" />
          </svg>
        </Link>
        <div className="w-9 h-9 rounded-full bg-slate-800 border border-slate-700 flex items-center justify-center font-semibold text-sm text-slate-200">
          {dev?.name.charAt(0).toUpperCase()}
        </div>
        <div>
          <h1 className="page-title">{dev?.name}</h1>
          <p className="page-subtitle">{dev?.email || dev?.github_username || "—"}</p>
        </div>
      </div>

      {/* Time window */}
      <div className="flex items-center gap-1.5 mb-6">
        {TIME_WINDOWS.map(({ h, label }) => (
          <button
            key={h}
            onClick={() => { setHours(h); load(h); }}
            className={h === hours ? "btn-secondary text-xs px-3" : "btn-ghost text-xs px-3"}
          >
            {label}
          </button>
        ))}
        <span className="ml-auto text-xs text-slate-600 self-center">
          {events.length} event{events.length !== 1 ? "s" : ""}
        </span>
      </div>

      {events.length === 0 ? (
        <div className="empty-state">
          <p className="text-slate-500 text-sm">No activity in this window</p>
        </div>
      ) : (
        <div className="relative">
          <div className="absolute left-[15px] top-2 bottom-2 w-px bg-slate-800" />
          {events.map((e) => (
            <div key={e.id} className="flex gap-4 pb-3 relative">
              <div className="w-8 h-8 rounded-full bg-slate-900 border border-slate-800 flex items-center justify-center shrink-0 z-10 mt-0.5">
                <svg className="w-3.5 h-3.5 text-slate-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75}
                    d={EVENT_ICON_PATH[e.event_type] || "M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"} />
                </svg>
              </div>
              <div className="flex-1 min-w-0 bg-slate-900 border border-slate-800 rounded-xl p-3.5">
                <div className="flex items-center gap-2 flex-wrap mb-1.5">
                  <span className={SOURCE_BADGE[e.source] || "badge-slate"}>{e.source}</span>
                  <span className="badge-slate text-xs">{e.event_type.replace(/_/g, " ")}</span>
                  <span className="text-xs text-slate-600 ml-auto">
                    {new Date(e.event_time).toLocaleString([], {
                      month: "short", day: "numeric",
                      hour: "2-digit", minute: "2-digit",
                    })}
                  </span>
                </div>
                <p className="text-slate-300 text-sm leading-relaxed">{e.summary}</p>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
