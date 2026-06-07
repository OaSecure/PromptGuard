import { dashboardRequest } from "./dashboardApi.js";

const DEFAULT_DASHBOARD_CSRF_COOKIE_NAME = "promptguard_dashboard_csrf";

export type DashboardUser = {
  id: string;
  login_id: string;
  username: string;
  department: string | null;
  display_name: string | null;
  role: string;
  status: string;
};

type DashboardCsrfResponse = {
  csrf_token: string;
};

type DashboardLoginResponse = {
  ok: boolean;
  user: DashboardUser;
  csrf_token: string;
  expires_at: string;
};

let csrfToken: string | null = null;

function csrfTokenFromCookie(): string | null {
  const cookieName =
    document.documentElement.dataset.promptguardDashboardCsrfCookieName?.trim() ||
    DEFAULT_DASHBOARD_CSRF_COOKIE_NAME;
  const cookies = document.cookie.split(";").map((cookie) => cookie.trim());
  const prefix = `${cookieName}=`;
  const value = cookies.find((cookie) => cookie.startsWith(prefix));
  return value ? decodeURIComponent(value.slice(prefix.length)) : null;
}

export function getDashboardCsrfToken(): string | null {
  return csrfToken ?? csrfTokenFromCookie();
}

export async function refreshDashboardCsrf(): Promise<string> {
  const response = await dashboardRequest<DashboardCsrfResponse>("/dashboard/session/csrf");
  csrfToken = response.csrf_token;
  return csrfToken;
}

export async function loginDashboardSession(loginId: string, password: string): Promise<DashboardUser> {
  const token = csrfToken ?? (await refreshDashboardCsrf());
  const response = await dashboardRequest<DashboardLoginResponse>("/dashboard/session/login", {
    method: "POST",
    csrfToken: token,
    body: {
      login_id: loginId,
      password,
    },
  });
  csrfToken = response.csrf_token;
  return response.user;
}

export async function getDashboardSessionMe(): Promise<DashboardUser> {
  return dashboardRequest<DashboardUser>("/dashboard/session/me");
}

export async function logoutDashboardSession(): Promise<void> {
  const token = getDashboardCsrfToken() ?? (await refreshDashboardCsrf());
  await dashboardRequest<void>("/dashboard/session/logout", {
    method: "POST",
    csrfToken: token,
  });
  csrfToken = null;
}
