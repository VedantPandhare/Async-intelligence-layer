"use client";

import { useEffect, useState } from "react";
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
    <div className="error-card"><p className="text-red-400 text-sm">{error}</p></div>
  );

  return (
    <div className="max-w-6xl">
      <div className="mb-8">
        <h1 className="page-title">Digest History</h1>
        <p className="page-subtitle">{digests.length} digest{digests.length !== 1 ? "s" : ""} on record</p>
      </div>

      {digests.length === 0 ? (
        <div className="empty-state">
          <p className="text-slate-500 text-sm">No digests yet. Run the pipeline to generate one.</p>
        </div>
      ) : (
        <div className="flex gap-4 h-[calc(100vh-180px)]">
          {/* Sidebar list */}
          <div className="w-48 shrink-0 space-y-0.5 overflow-y-auto pr-1">
            {digests.map((d) => (
              <button
                key={d.id}
                onClick={() => setSelected(d)}
                className={`w-full text-left px-3 py-2.5 rounded-lg text-sm transition-colors ${
                  selected?.id === d.id
                    ? "bg-slate-800 text-white"
                    : "text-slate-500 hover:bg-slate-800/50 hover:text-slate-300"
                }`}
              >
                <div className="font-medium text-xs">{d.digest_date}</div>
                <div className="text-xs mt-0.5 opacity-60">
                  {d.delivered ? "Delivered" : "Not sent"}
                </div>
              </button>
            ))}
          </div>

          {/* Content panel */}
          {selected && (
            <div className="flex-1 card overflow-y-auto">
              <div className="flex items-center gap-3 mb-5 pb-4 border-b border-slate-800 sticky top-0 bg-slate-900 -mx-5 px-5 pt-0 -mt-5 pt-5 z-10">
                <span className="font-semibold text-sm text-white">{selected.digest_date}</span>
                {selected.delivered ? (
                  <span className="badge-green">Delivered</span>
                ) : (
                  <span className="badge-slate">Not delivered</span>
                )}
                <span className="text-xs text-slate-600 ml-auto">
                  {new Date(selected.generated_at).toLocaleString([], {
                    month: "short", day: "numeric",
                    hour: "2-digit", minute: "2-digit",
                  })}
                </span>
              </div>
              {selected.markdown_output ? (
                <MarkdownRenderer content={selected.markdown_output} />
              ) : (
                <p className="text-slate-600 italic text-sm">Content stripped by retention policy.</p>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
