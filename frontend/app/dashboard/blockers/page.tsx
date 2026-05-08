"use client";

import { useEffect, useState } from "react";
import { apiFetch, type Blocker } from "@/lib/api";
import { getOrgId } from "@/lib/auth";
import Spinner from "@/components/Spinner";

const SEVERITY_CLASS: Record<string, string> = {
  critical: "badge-red",
  high:     "badge-orange",
  medium:   "badge-yellow",
  low:      "badge-blue",
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

  async function resolve(blockerId: string) {
    setResolving(blockerId);
    try {
      await apiFetch(`/digests/blockers/${blockerId}/resolve`, { method: "PATCH" });
      setBlockers((prev) => prev.filter((b) => b.id !== blockerId));
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
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1>Active Blockers</h1>
          <p className="text-slate-400 text-sm mt-1">
            {blockers.length} unresolved {blockers.length === 1 ? "blocker" : "blockers"}
          </p>
        </div>
        <button onClick={loadBlockers} className="btn-ghost">
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
              d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
          </svg>
          Refresh
        </button>
      </div>

      {error && (
        <div className="card border-red-800 bg-red-900/10 mb-4">
          <p className="text-red-400 text-sm">{error}</p>
        </div>
      )}

      {blockers.length === 0 ? (
        <div className="card text-center py-16">
          <svg className="w-12 h-12 text-green-700 mx-auto mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
              d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <p className="text-slate-400">No active blockers.</p>
          <p className="text-slate-600 text-sm mt-1">All clear!</p>
        </div>
      ) : (
        <div className="space-y-3">
          {blockers.map((b) => (
            <div key={b.id} className="card flex items-start gap-4">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap mb-2">
                  <span className={SEVERITY_CLASS[b.severity] || "badge-slate"}>
                    {b.severity}
                  </span>
                  <span className="badge-slate">{b.blocker_type}</span>
                  {b.intervention_sent && (
                    <span className="badge-blue">Intervention sent</span>
                  )}
                </div>
                <p className="text-slate-200 text-sm">{b.description}</p>
                <p className="text-slate-500 text-xs mt-2">
                  Detected {new Date(b.detected_at).toLocaleString()}
                </p>
              </div>
              <button
                onClick={() => resolve(b.id)}
                disabled={resolving === b.id}
                className="btn-ghost shrink-0 text-green-400 hover:bg-green-900/20 hover:text-green-300"
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
          ))}
        </div>
      )}
    </div>
  );
}
