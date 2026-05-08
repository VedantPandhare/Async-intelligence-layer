"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { apiFetch, type Developer } from "@/lib/api";
import { getOrgId } from "@/lib/auth";
import Spinner from "@/components/Spinner";

export default function DevelopersPage() {
  const [developers, setDevelopers] = useState<Developer[]>([]);
  const [loading, setLoading] = useState(true);
  const [toggling, setToggling] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [showAll, setShowAll] = useState(false);

  const orgId = getOrgId();

  async function load() {
    if (!orgId) return;
    try {
      // Fetch all developers including inactive
      const data = await apiFetch<Developer[]>(`/developers/${orgId}`);
      setDevelopers(data);
    } catch (err) {
      setError(String(err));
    } finally {
      setLoading(false);
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

  return (
    <div className="max-w-4xl">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1>Developers</h1>
          <p className="text-slate-400 text-sm mt-1">
            {developers.filter((d) => d.is_active).length} active · {developers.filter((d) => !d.is_active).length} opted out
          </p>
        </div>
        <button onClick={() => setShowAll(!showAll)} className="btn-ghost text-sm">
          {showAll ? "Hide opted-out" : "Show all"}
        </button>
      </div>

      {error && (
        <div className="card border-red-800 bg-red-900/10 mb-4">
          <p className="text-red-400 text-sm">{error}</p>
        </div>
      )}

      {displayed.length === 0 ? (
        <div className="card text-center py-16 text-slate-400">No developers found.</div>
      ) : (
        <div className="space-y-2">
          {displayed.map((dev) => (
            <div
              key={dev.id}
              className={`card flex items-center gap-4 ${!dev.is_active ? "opacity-50" : ""}`}
            >
              <div className="w-9 h-9 rounded-full bg-slate-700 flex items-center justify-center text-sm font-semibold shrink-0">
                {dev.name.charAt(0).toUpperCase()}
              </div>

              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="font-medium text-slate-100">{dev.name}</span>
                  {dev.role && <span className="badge-slate">{dev.role}</span>}
                  {!dev.is_active && <span className="badge-orange">Opted out</span>}
                </div>
                <div className="flex gap-3 mt-0.5">
                  {dev.github_username && (
                    <span className="text-xs text-slate-500">gh: {dev.github_username}</span>
                  )}
                  {dev.email && (
                    <span className="text-xs text-slate-500">{dev.email}</span>
                  )}
                </div>
              </div>

              <div className="flex items-center gap-2 shrink-0">
                <Link
                  href={`/dashboard/developers/${dev.id}`}
                  className="btn-ghost text-xs"
                >
                  Timeline
                </Link>
                <button
                  onClick={() => toggleActive(dev)}
                  disabled={toggling === dev.id}
                  className={dev.is_active ? "btn-danger text-xs" : "btn-ghost text-xs text-green-400"}
                >
                  {toggling === dev.id ? (
                    <Spinner className="w-3 h-3" />
                  ) : dev.is_active ? (
                    "Opt out"
                  ) : (
                    "Opt in"
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
