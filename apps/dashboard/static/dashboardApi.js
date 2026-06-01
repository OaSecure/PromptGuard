const DEFAULT_API_BASE_URL = "http://localhost:8000";
export class DashboardApiError extends Error {
    status;
    constructor(status) {
        super("Dashboard API request failed");
        this.name = "DashboardApiError";
        this.status = status;
    }
}
export function dashboardApiBaseUrl() {
    const configured = document.documentElement.dataset.promptguardApiBaseUrl?.trim();
    return (configured || DEFAULT_API_BASE_URL).replace(/\/+$/, "");
}
export async function dashboardRequest(path, options = {}) {
    const headers = new Headers({ Accept: "application/json" });
    if (options.body !== undefined) {
        headers.set("Content-Type", "application/json");
    }
    if (options.csrfToken) {
        headers.set("X-CSRF-Token", options.csrfToken);
    }
    let response;
    try {
        response = await fetch(`${dashboardApiBaseUrl()}${path}`, {
            method: options.method ?? "GET",
            headers,
            body: options.body === undefined ? undefined : JSON.stringify(options.body),
            credentials: "include",
        });
    }
    catch {
        throw new DashboardApiError(0);
    }
    if (!response.ok) {
        throw new DashboardApiError(response.status);
    }
    if (response.status === 204) {
        return undefined;
    }
    try {
        return (await response.json());
    }
    catch {
        throw new DashboardApiError(response.status);
    }
}
