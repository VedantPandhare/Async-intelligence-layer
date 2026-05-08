"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { apiFetch, type Digest } from "@/lib/api";
import { getOrgId } from "@/lib/auth";
import Spinner from "@/components/Spinner";
import MarkdownRenderer from "@/components/MarkdownRenderer";

export default function DigestsPage() {
  const [digests, setDigests] = useState<Digest[]>([]);
  const [selected, setSelected] = useState<Digest | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const orgId = getOrgId();

  useEffect(() => {
    if (!orgId) return;
    apiFetch<Digest[]>(`/digests/${orgId}?limit=30`)
      .then((data) => {
        setDigests(data);
        if (data.length) setSelected(data[0]);
      })
      .catch((err) => setError(String(err)))
      .finally(() => setLoading(false));
  }, [orgId]);

  if (loading) return (
    <div className="flex items-center justify-center h-64"><Spinner /></div>
  );

  if (error) return (
    <div className="card border-red-800 bg-red-900/10">
      <p className="text-red-400 text-sm">{error}</p>
    </div>
  );

  return (
    <div className="max-w-6xl">
      <h1 className="mb-6">Digest History</h1>

      {digests.length === 0 ? (
        <div className="card text-center py-16 text-slate-400">No digests found.</div>
      ) : (
        <div className="flex gap-5">
          {/* Sidebar list */}
          <div className="w-52 shrink-0 space-y-1">
            {digests.map((d) => (
              <button
                key={d.id}
                onClick={() => setSelected(d)}
                className={`w-full text-left px-3 py-2.5 rounded-lg text-sm transition-colors ${
                  selected?.id === d.id
                    ? "bg-brand-600/20 text-brand-400"
                    : "text-slate-400 hover:bg-slate-800 hover:text-white"
                }`}
              >
                <div className="font-medium">{d.digest_date}</div>
                <div className="text-xs mt-0.5 opacity-60">
                  {d.delivered ? "Delivered" : "Not sent"}
                </div>
              </button>
            ))}
          </div>

          {/* Content panel */}
          {selected && (
            <div className="flex-1 card">
              <div className="flex items-center gap-3 mb-5 pb-4 border-b border-slate-800">
                <span className="font-semibold">{selected.digest_date}</span>
                {selected.delivered ? (
                  <span className="badge-green">Delivered</span>
                ) : (
                  <span className="badge-slate">Not delivered</span>
                )}
                <span className="text-xs text-slate-500 ml-auto">
                  {new Date(selected.generated_at).toLocaleString()}
                </span>
              </div>
              {selected.markdown_output ? (
                <MarkdownRenderer content={selected.markdown_output} />
              ) : (
                <p className="text-slate-500 italic text-sm">Content stripped by retention policy.</p>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
