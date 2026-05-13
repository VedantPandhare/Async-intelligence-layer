"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { apiFetch, type Developer } from "@/lib/api";
import { getOrgId } from "@/lib/auth";
import Spinner from "@/components/Spinner";

function Avatar({ name }: { name: string }) {
  return (
    <div className="w-8 h-8 rounded-full bg-slate-800 border border-slate-700 flex items-center justify-center text-xs font-semibold text-slate-300 shrink-0">
      {name.charAt(0).toUpperCase()}
    </div>
  );
}

export default function DevelopersPage() {
  const [developers, setDevelopers] = useState<Developer[]>([]);
  const [loading, setLoading] = useState(true);
  const [toggling, setToggling] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [showAll, setShowAll] = useState(false);
  const orgId = getOrgId();

  async function load() {
    if (!orgId) return;
    try {
      const data = await apiFetch<Developer[]>(`/developers/${orgId}`);
      setDevelopers(data);
    } catch (err) {
      setError(String(err));
    } finally {
      setLoading(false);
    }
  }

  async function deleteDeveloper(dev: Developer) {
    if (!orgId) return;
    if (!confirm(`Remove ${dev.name} from this workspace?`)) return;
    setDeleting(dev.id);
    try {
      await apiFetch(`/developers/${orgId}/${dev.id}`, { method: "DELETE" });
      setDevelopers((prev) => prev.filter((d) => d.id !== dev.id));
    } catch (err) {
      setError(String(err));
    } finally {
      setDeleting(null);
    }
  }

  async function toggleActive(dev: Developer) {
    if (!orgId) return;
    setToggling(dev.id);
    const endpoint = dev.is_active ? "opt-out" : "opt-in";
    try {
      await apiFetch(`/developers/${orgId}/${dev.id}/${endpoint}`, { method: "PATCH" });
      setDevelopers((prev) =>
        prev.map((d) => (d.id === dev.id ? { ...d, is_active: !d.is_active } : d))
      );
    } catch (err) {
      setError(String(err));
    } finally {
      setToggling(null);
    }
  }

  useEffect(() => { load(); }, [orgId]);

  if (loading) return (
    <div className="flex items-center justify-center h-64"><Spinner /></div>
  );

  const displayed = showAll ? developers : developers.filter((d) => d.is_active);
  const activeCount = developers.filter((d) => d.is_active).length;
  const inactiveCount = developers.length - activeCount;

  return (
    <div className="max-w-4xl">
      <div className="page-header">
        <div>
          <h1 className="page-title">Developers</h1>
          <p className="page-subtitle">
            {activeCount} active
            {inactiveCount > 0 && ` · ${inactiveCount} opted out`}
          </p>
        </div>
        {inactiveCount > 0 && (
          <button onClick={() => setShowAll(!showAll)} className="btn-ghost text-xs">
            {showAll ? "Hide inactive" : "Show all"}
          </button>
        )}
      </div>

      {error && (
        <div className="error-card mb-4">
          <p className="text-red-400 text-sm">{error}</p>
        </div>
      )}

      {displayed.length === 0 ? (
        <div className="empty-state">
          <p className="text-slate-500 text-sm">No developers found.</p>
        </div>
      ) : (
        <div className="space-y-1.5">
          {displayed.map((dev) => (
            <div
              key={dev.id}
              className={`card flex items-center gap-3 py-3.5 ${!dev.is_active ? "opacity-50" : ""}`}
            >
              <Avatar name={dev.name} />

              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-sm font-medium text-slate-100">{dev.name}</span>
                  {dev.role && <span className="badge-slate text-xs">{dev.role}</span>}
                  {!dev.is_active && <span className="badge-orange text-xs">Inactive</span>}
                </div>
                <div className="flex gap-3 mt-0.5">
                  {dev.github_username && (
                    <span className="text-xs text-slate-600">@{dev.github_username}</span>
                  )}
                  {dev.email && (
                    <span className="text-xs text-slate-600">{dev.email}</span>
                  )}
                </div>
              </div>

              <div className="flex items-center gap-1.5 shrink-0">
                <Link href={`/dashboard/developers/${dev.id}`} className="btn-ghost text-xs px-3">
                  Timeline
                </Link>
                <button
                  onClick={() => toggleActive(dev)}
                  disabled={toggling === dev.id}
                  className={dev.is_active ? "btn-secondary text-xs px-3" : "btn-secondary text-xs px-3 text-green-400"}
                >
                  {toggling === dev.id ? (
                    <Spinner className="w-3 h-3" />
                  ) : dev.is_active ? (
                    "Opt out"
                  ) : (
                    "Opt in"
                  )}
                </button>
                <button
                  onClick={() => deleteDeveloper(dev)}
                  disabled={deleting === dev.id}
                  className="btn-ghost text-xs px-2 text-slate-600 hover:text-red-400"
                  title="Remove from workspace"
                >
                  {deleting === dev.id ? <Spinner className="w-3 h-3" /> : (
                    <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                    </svg>
                  )}
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
