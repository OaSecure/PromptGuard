import { dashboardRequest } from "./dashboardApi.js";
const DEFAULT_DASHBOARD_CSRF_COOKIE_NAME = "promptguard_dashboard_csrf";
let csrfToken = null;
function csrfTokenFromCookie() {
    const cookieName = document.documentElement.dataset.promptguardDashboardCsrfCookieName?.trim() ||
        DEFAULT_DASHBOARD_CSRF_COOKIE_NAME;
    const cookies = document.cookie.split(";").map((cookie) => cookie.trim());
    const prefix = `${cookieName}=`;
    const value = cookies.find((cookie) => cookie.startsWith(prefix));
    return value ? decodeURIComponent(value.slice(prefix.length)) : null;
}
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
export async function logoutDashboardSession() {
    const token = csrfToken ?? csrfTokenFromCookie() ?? (await refreshDashboardCsrf());
    await dashboardRequest("/dashboard/session/logout", {
        method: "POST",
        csrfToken: token,
    });
    csrfToken = null;
}
