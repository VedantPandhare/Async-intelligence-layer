"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { apiFetch, type Developer, type TimelineEvent } from "@/lib/api";
import { getOrgId } from "@/lib/auth";
import Spinner from "@/components/Spinner";

const SOURCE_COLOR: Record<string, string> = {
  github: "badge-blue",
  slack:  "badge-green",
  jira:   "badge-orange",
};

const EVENT_ICONS: Record<string, string> = {
  commit:          "M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4",
  pull_request:    "M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4",
  ci_run:          "M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z",
  slack_message:   "M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z",
  jira_issue:      "M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2",
};

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

  function changeWindow(h: number) {
    setHours(h);
    load(h);
  }

  if (loading) return (
    <div className="flex items-center justify-center h-64"><Spinner /></div>
  );

  if (error) return (
    <div className="card border-red-800 bg-red-900/10">
      <p className="text-red-400 text-sm">{error}</p>
    </div>
  );

  return (
    <div className="max-w-3xl">
      <div className="flex items-center gap-3 mb-6">
        <Link href="/dashboard/developers" className="text-slate-500 hover:text-slate-300 transition-colors">
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
          </svg>
        </Link>
        <div className="w-10 h-10 rounded-full bg-slate-700 flex items-center justify-center font-semibold">
          {dev?.name.charAt(0).toUpperCase()}
        </div>
        <div>
          <h1>{dev?.name}</h1>
          <p className="text-slate-400 text-sm">{dev?.email || dev?.github_username || "—"}</p>
        </div>
      </div>

      {/* Time window selector */}
      <div className="flex gap-2 mb-6">
        {[8, 24, 48, 168].map((h) => (
          <button
            key={h}
            onClick={() => changeWindow(h)}
            className={hours === h ? "btn-primary text-xs" : "btn-ghost text-xs"}
          >
            {h < 24 ? `${h}h` : h === 168 ? "7 days" : `${h / 24}d`}
          </button>
        ))}
        <span className="ml-auto text-xs text-slate-500 self-center">
          {events.length} events
        </span>
      </div>

      {events.length === 0 ? (
        <div className="card text-center py-16 text-slate-400">
          No activity in the last {hours < 24 ? `${hours} hours` : `${hours / 24} days`}.
        </div>
      ) : (
        <div className="relative space-y-0">
          <div className="absolute left-[18px] top-4 bottom-4 w-px bg-slate-800" />
          {events.map((e) => (
            <div key={e.id} className="flex gap-4 pb-4 relative">
              <div className="w-9 h-9 rounded-full bg-slate-800 border border-slate-700 flex items-center justify-center shrink-0 z-10">
                <svg className="w-4 h-4 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                    d={EVENT_ICONS[e.event_type] || "M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"} />
                </svg>
              </div>
              <div className="flex-1 min-w-0 bg-slate-900 border border-slate-800 rounded-xl p-3.5">
                <div className="flex items-center gap-2 flex-wrap mb-1">
                  <span className={SOURCE_COLOR[e.source] || "badge-slate"}>{e.source}</span>
                  <span className="badge-slate text-xs">{e.event_type.replace(/_/g, " ")}</span>
                  <span className="text-xs text-slate-500 ml-auto">
                    {new Date(e.event_time).toLocaleString()}
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
