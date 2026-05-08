"use client";

import { useEffect, useState } from "react";
import { apiFetch, type Digest } from "@/lib/api";
import { getOrgId } from "@/lib/auth";
import MarkdownRenderer from "@/components/MarkdownRenderer";
import Spinner from "@/components/Spinner";

export default function TodayPage() {
  const [digest, setDigest] = useState<Digest | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [triggering, setTriggering] = useState(false);

  const orgId = getOrgId();

  async function load() {
    if (!orgId) return;
    setLoading(true);
    setError("");
    try {
      const d = await apiFetch<Digest>(`/digests/${orgId}/today`);
      setDigest(d);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      if (msg.startsWith("404")) setDigest(null);
      else setError(msg);
    } finally {
      setLoading(false);
    }
  }

  async function triggerDigest() {
    if (!orgId) return;
    setTriggering(true);
    try {
      const result = await apiFetch<{ markdown_output: string }>(`/digests/${orgId}/trigger`, {
        method: "POST",
      });
      setDigest({ ...digest!, markdown_output: result.markdown_output } as Digest);
      await load();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to trigger digest");
    } finally {
      setTriggering(false);
    }
  }

  useEffect(() => {
    load();
  }, [orgId]);

  const today = new Date().toLocaleDateString("en-US", {
    weekday: "long", year: "numeric", month: "long", day: "numeric",
  });

  return (
    <div className="max-w-4xl">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1>Today&apos;s Digest</h1>
          <p className="text-slate-400 text-sm mt-1">{today}</p>
        </div>
        <div className="flex gap-3">
          <button onClick={load} className="btn-ghost" disabled={loading}>
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
            Refresh
          </button>
          <button onClick={triggerDigest} className="btn-primary" disabled={triggering}>
            {triggering && <Spinner className="w-3.5 h-3.5" />}
            Run pipeline
          </button>
        </div>
      </div>

      {loading && (
        <div className="flex items-center justify-center h-64">
          <Spinner />
        </div>
      )}

      {error && (
        <div className="card border-red-800 bg-red-900/10">
          <p className="text-red-400 text-sm">{error}</p>
        </div>
      )}

      {!loading && !error && !digest && (
        <div className="card text-center py-16">
          <svg className="w-12 h-12 text-slate-700 mx-auto mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
              d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
          </svg>
          <p className="text-slate-400">No digest generated yet for today.</p>
          <p className="text-slate-600 text-sm mt-1">Run the pipeline to generate one.</p>
        </div>
      )}

      {!loading && digest?.markdown_output && (
        <div className="card">
          <div className="flex items-center justify-between mb-5 pb-4 border-b border-slate-800">
            <div className="flex items-center gap-2">
              {digest.delivered ? (
                <span className="badge-green">Delivered</span>
              ) : (
                <span className="badge-slate">Not delivered</span>
              )}
              <span className="text-xs text-slate-500">
                Generated {new Date(digest.generated_at).toLocaleTimeString()}
              </span>
            </div>
          </div>
          <MarkdownRenderer content={digest.markdown_output} />
        </div>
      )}
    </div>
  );
}
