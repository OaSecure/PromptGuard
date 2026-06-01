import { dashboardRequest } from "./dashboardApi.js";
let csrfToken = null;
export async function refreshDashboardCsrf() {
    const response = await dashboardRequest("/dashboard/session/csrf");
    csrfToken = response.csrf_token;
    return csrfToken;
}
export async function loginDashboardSession(loginId, password) {
    const token = csrfToken ?? (await refreshDashboardCsrf());
    const response = await dashboardRequest("/dashboard/session/login", {
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
export async function getDashboardSessionMe() {
    return dashboardRequest("/dashboard/session/me");
}
