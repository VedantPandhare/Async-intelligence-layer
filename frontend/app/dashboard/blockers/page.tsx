"use client";

import { useEffect, useState } from "react";
import { apiFetch, type Blocker } from "@/lib/api";
import { getOrgId } from "@/lib/auth";
import Spinner from "@/components/Spinner";

const SEVERITY: Record<string, { badge: string; dot: string }> = {
  critical: { badge: "badge-red",    dot: "bg-red-400" },
  high:     { badge: "badge-orange", dot: "bg-orange-400" },
  medium:   { badge: "badge-yellow", dot: "bg-yellow-400" },
  low:      { badge: "badge-blue",   dot: "bg-blue-400" },
};

export default function BlockersPage() {
  const [blockers, setBlockers] = useState<Blocker[]>([]);
  const [loading, setLoading] = useState(true);
  const [resolving, setResolving] = useState<string | null>(null);
  const [error, setError] = useState("");
  const orgId = getOrgId();

  async function loadBlockers() {
    if (!orgId) return;
    try {
      const data = await apiFetch<Blocker[]>(`/digests/${orgId}/blockers`);
      setBlockers(data);
    } catch (err) {
      setError(String(err));
    } finally {
      setLoading(false);
    }
  }

  async function resolve(id: string) {
    setResolving(id);
    try {
      await apiFetch(`/digests/blockers/${id}/resolve`, { method: "PATCH" });
      setBlockers((prev) => prev.filter((b) => b.id !== id));
    } catch (err) {
      setError(String(err));
    } finally {
      setResolving(null);
    }
  }

  useEffect(() => { loadBlockers(); }, [orgId]);

  if (loading) return (
    <div className="flex items-center justify-center h-64"><Spinner /></div>
  );

  return (
    <div className="max-w-4xl">
      <div className="page-header">
        <div>
          <h1 className="page-title">Active Blockers</h1>
          <p className="page-subtitle">
            {blockers.length} unresolved {blockers.length === 1 ? "blocker" : "blockers"}
          </p>
        </div>
        <button onClick={loadBlockers} className="btn-ghost">
          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
              d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
          </svg>
          Refresh
        </button>
      </div>

      {error && (
        <div className="error-card mb-4">
          <p className="text-red-400 text-sm">{error}</p>
        </div>
      )}

      {blockers.length === 0 ? (
        <div className="empty-state">
          <div className="w-10 h-10 bg-slate-800 rounded-xl flex items-center justify-center mx-auto mb-4">
            <svg className="w-5 h-5 text-green-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75}
                d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          </div>
          <p className="text-slate-300 font-medium text-sm">All clear</p>
          <p className="text-slate-600 text-xs mt-1">No active blockers detected</p>
        </div>
      ) : (
        <div className="space-y-2.5">
          {blockers.map((b) => {
            const s = SEVERITY[b.severity] || { badge: "badge-slate", dot: "bg-slate-500" };
            return (
              <div key={b.id} className="card flex items-start gap-4">
                <div className={`mt-0.5 w-1.5 h-1.5 rounded-full ${s.dot} shrink-0 mt-2`} />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap mb-1.5">
                    <span className={s.badge}>{b.severity}</span>
                    <span className="badge-slate">{b.blocker_type.replace(/_/g, " ")}</span>
                    {b.intervention_sent && (
                      <span className="badge-blue">Intervention sent</span>
                    )}
                  </div>
                  <p className="text-slate-200 text-sm leading-relaxed">{b.description}</p>
                  <p className="text-slate-600 text-xs mt-2">
                    {new Date(b.detected_at).toLocaleString([], {
                      month: "short", day: "numeric",
                      hour: "2-digit", minute: "2-digit",
                    })}
                  </p>
                </div>
                <button
                  onClick={() => resolve(b.id)}
                  disabled={resolving === b.id}
                  className="btn-ghost shrink-0 text-xs text-slate-500 hover:text-green-400"
                >
                  {resolving === b.id ? (
                    <Spinner className="w-3.5 h-3.5" />
                  ) : (
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                    </svg>
                  )}
                  Resolve
                </button>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
