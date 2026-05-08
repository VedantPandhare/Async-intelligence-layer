import { clearAuth, getOrgId, getToken, setToken } from "./auth";

const BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

let _refreshPromise: Promise<void> | null = null;

async function _tryRefresh(): Promise<void> {
  const refreshToken = localStorage.getItem("refresh_token");
  if (!refreshToken) throw new Error("No refresh token");

  const res = await fetch(`${BASE}/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: refreshToken }),
  });

  if (!res.ok) {
    clearAuth();
    localStorage.removeItem("refresh_token");
    window.location.href = "/login";
    throw new Error("Session expired");
  }

  const data = await res.json();
  setToken(data.access_token);
  localStorage.setItem("refresh_token", data.refresh_token);
}

export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const doFetch = async (): Promise<Response> => {
    const token = getToken();
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      ...(init.headers as Record<string, string>),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    };
    return fetch(`${BASE}${path}`, { ...init, headers });
  };

  let res = await doFetch();

  // On 401, attempt a single token refresh then retry
  if (res.status === 401) {
    if (!_refreshPromise) {
      _refreshPromise = _tryRefresh().finally(() => { _refreshPromise = null; });
    }
    await _refreshPromise;
    res = await doFetch();
  }

  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(`${res.status}: ${text}`);
  }

  return res.json() as Promise<T>;
}

// ─── Typed helpers ────────────────────────────────────────────────────────────

export type Digest = {
  id: string;
  digest_date: string;
  generated_at: string;
  delivered: boolean;
  markdown_output: string;
  content?: Record<string, unknown>;
};

export type Blocker = {
  id: string;
  developer_id: string;
  severity: string;
  blocker_type: string;
  description: string;
  detected_at: string;
  intervention_sent: boolean;
};

export type Developer = {
  id: string;
  name: string;
  email: string | null;
  github_username: string | null;
  slack_user_id: string | null;
  jira_account_id: string | null;
  role: string | null;
  is_active: boolean;
};

export type TimelineEvent = {
  id: string;
  source: string;
  event_type: string;
  event_time: string;
  summary: string;
  payload: Record<string, unknown>;
};

export type OrgSettings = {
  id: string;
  name: string;
  slug: string;
  digest_time: string;
  timezone: string;
  settings: Record<string, unknown>;
};
