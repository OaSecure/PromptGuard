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

function csrfTokenFromCookie(): string | null {
  const cookieName =
    document.documentElement.dataset.promptguardDashboardCsrfCookieName?.trim() ||
    DEFAULT_DASHBOARD_CSRF_COOKIE_NAME;
  const cookies = document.cookie.split(";").map((cookie) => cookie.trim());
  const prefix = `${cookieName}=`;
  const value = cookies.find((cookie) => cookie.startsWith(prefix));
  return value ? decodeURIComponent(value.slice(prefix.length)) : null;
}

type DashboardSessionRequest = <T>(
  path: string,
  options?: {
    method?: "GET" | "POST" | "PATCH" | "DELETE";
    body?: unknown;
    csrfToken?: string | null;
  },
) => Promise<T>;

type DashboardSessionClientDeps = {
  request: DashboardSessionRequest;
  cookieToken: () => string | null;
};

export type DashboardSessionClient = {
  getDashboardCsrfToken: () => string | null;
  refreshDashboardCsrf: () => Promise<string>;
  loginDashboardSession: (loginId: string, password: string) => Promise<DashboardUser>;
  getDashboardSessionMe: () => Promise<DashboardUser>;
  logoutDashboardSession: () => Promise<void>;
};

export function createDashboardSessionClient(deps: DashboardSessionClientDeps): DashboardSessionClient {
  let csrfToken: string | null = null;

  async function refreshDashboardCsrf(): Promise<string> {
    const response = await deps.request<DashboardCsrfResponse>("/dashboard/session/csrf");
    csrfToken = response.csrf_token;
    return csrfToken;
  }

  return {
    getDashboardCsrfToken(): string | null {
      return csrfToken ?? deps.cookieToken();
    },

    refreshDashboardCsrf,

    async loginDashboardSession(loginId: string, password: string): Promise<DashboardUser> {
      const token = csrfToken ?? (await refreshDashboardCsrf());
      const response = await deps.request<DashboardLoginResponse>("/dashboard/session/login", {
        method: "POST",
        csrfToken: token,
        body: {
          login_id: loginId,
          password,
        },
      });
      csrfToken = response.csrf_token;
      return response.user;
    },

    async getDashboardSessionMe(): Promise<DashboardUser> {
      return deps.request<DashboardUser>("/dashboard/session/me");
    },

    async logoutDashboardSession(): Promise<void> {
      const token = csrfToken ?? (await refreshDashboardCsrf());
      await deps.request<void>("/dashboard/session/logout", {
        method: "POST",
        csrfToken: token,
      });
      csrfToken = null;
    },
  };
}

const defaultSessionClient = createDashboardSessionClient({
  request: dashboardRequest,
  cookieToken: csrfTokenFromCookie,
});

export const getDashboardCsrfToken = defaultSessionClient.getDashboardCsrfToken;
export const refreshDashboardCsrf = defaultSessionClient.refreshDashboardCsrf;
export const loginDashboardSession = defaultSessionClient.loginDashboardSession;
export const getDashboardSessionMe = defaultSessionClient.getDashboardSessionMe;
export const logoutDashboardSession = defaultSessionClient.logoutDashboardSession;
