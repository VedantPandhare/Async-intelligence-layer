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

// ─── Auth helpers ─────────────────────────────────────────────────────────────

export async function loginWithEmail(
  email: string,
  password: string,
): Promise<{ access_token: string; refresh_token: string; org_id: string; expires_in: number }> {
  const res = await fetch(`${BASE}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || "Invalid email or password");
  }
  return res.json();
}

export async function registerUser(payload: {
  name: string;
  email: string;
  password: string;
  org_name: string;
}): Promise<{ access_token: string; refresh_token: string; org_id: string; expires_in: number }> {
  const res = await fetch(`${BASE}/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || "Registration failed");
  }
  return res.json();
}

// ─── Integrations ─────────────────────────────────────────────────────────────

export type IntegrationStatus = {
  connected: boolean;
  connected_at?: string;
  metadata?: {
    github_username?: string;
    github_orgs?: string[];
    workspace_name?: string;
    workspace_id?: string;
    channels?: { id: string; name: string }[];
    scope?: string;
  };
};

export type IntegrationsResponse = {
  github: IntegrationStatus;
  slack: IntegrationStatus;
  jira: IntegrationStatus;
};

export async function getIntegrations(orgId: string): Promise<IntegrationsResponse> {
  return apiFetch<IntegrationsResponse>(`/org/${orgId}/integrations`);
}

export async function disconnectIntegration(orgId: string, provider: string): Promise<void> {
  await apiFetch(`/org/${orgId}/integrations/${provider}`, { method: "DELETE" });
}

/** Returns the GitHub OAuth authorization URL. Open it with window.location.href. */
export async function getGithubConnectUrl(
  orgId: string,
  redirectTo: string = "/onboarding",
): Promise<string> {
  const data = await apiFetch<{ authorization_url: string }>(
    `/auth/github/connect/${orgId}?redirect_to=${encodeURIComponent(redirectTo)}`,
  );
  return data.authorization_url;
}

/** Returns the Slack OAuth authorization URL. Open it with window.location.href. */
export async function getSlackConnectUrl(
  orgId: string,
  redirectTo: string = "/onboarding",
): Promise<string> {
  const data = await apiFetch<{ authorization_url: string }>(
    `/auth/slack/connect/${orgId}?redirect_to=${encodeURIComponent(redirectTo)}`,
  );
  return data.authorization_url;
}

// ─── Developer import ─────────────────────────────────────────────────────────

export type ImportResult = {
  imported: number;
  skipped: number;
  developers: { name: string; github_username: string }[];
};

export async function importFromGitHub(orgId: string): Promise<ImportResult> {
  return apiFetch<ImportResult>(`/developers/${orgId}/import-github`, { method: "POST" });
}

export async function listGithubOrgs(orgId: string): Promise<{ orgs: string[] }> {
  return apiFetch<{ orgs: string[] }>(`/developers/${orgId}/github-orgs`);
}

// ─── Types ────────────────────────────────────────────────────────────────────

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
  settings: {
    slack_channel?: string;
    github_org?: string;
    github_repos?: string[];
    slack_read_channels?: string[];
    [key: string]: unknown;
  };
};
