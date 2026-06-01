import { dashboardRequest } from "./dashboardApi.js";

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
