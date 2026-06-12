import { dashboardRequest } from "./dashboardApi.js";
const DEFAULT_DASHBOARD_CSRF_COOKIE_NAME = "promptguard_dashboard_csrf";
function csrfTokenFromCookie() {
    const cookieName = document.documentElement.dataset.promptguardDashboardCsrfCookieName?.trim() ||
        DEFAULT_DASHBOARD_CSRF_COOKIE_NAME;
    const cookies = document.cookie.split(";").map((cookie) => cookie.trim());
    const prefix = `${cookieName}=`;
    const value = cookies.find((cookie) => cookie.startsWith(prefix));
    return value ? decodeURIComponent(value.slice(prefix.length)) : null;
}
export function createDashboardSessionClient(deps) {
    let csrfToken = null;
    async function refreshDashboardCsrf() {
        const response = await deps.request("/dashboard/session/csrf");
        csrfToken = response.csrf_token;
        return csrfToken;
    }
    return {
        getDashboardCsrfToken() {
            return csrfToken ?? deps.cookieToken();
        },
        refreshDashboardCsrf,
        async loginDashboardSession(loginId, password) {
            const token = csrfToken ?? (await refreshDashboardCsrf());
            const response = await deps.request("/dashboard/session/login", {
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
        async getDashboardSessionMe() {
            return deps.request("/dashboard/session/me");
        },
        async logoutDashboardSession() {
            const token = csrfToken ?? (await refreshDashboardCsrf());
            await deps.request("/dashboard/session/logout", {
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
