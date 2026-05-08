export const getToken = (): string | null => {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("jwt_token");
};

export const setToken = (token: string): void => {
  localStorage.setItem("jwt_token", token);
};

export const getOrgId = (): string | null => {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("org_id");
};

export const setOrgId = (orgId: string): void => {
  localStorage.setItem("org_id", orgId);
};

export const clearAuth = (): void => {
  localStorage.removeItem("jwt_token");
  localStorage.removeItem("org_id");
};

export const isAuthenticated = (): boolean => {
  return !!getToken() && !!getOrgId();
};
