type RequestOptions = {
  method?: "GET" | "POST" | "PATCH" | "DELETE";
  body?: unknown;
  csrfToken?: string | null;
};

export class DashboardApiError extends Error {
  readonly status: number;

  constructor(status: number) {
    super("Dashboard API request failed");
    this.name = "DashboardApiError";
    this.status = status;
  }
}

export function dashboardApiBaseUrl(): string {
  const configured = document.documentElement.dataset.promptguardApiBaseUrl?.trim();
  return configured ? configured.replace(/\/+$/, "") : "";
}

export async function dashboardRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const headers = new Headers({ Accept: "application/json" });

  if (options.body !== undefined) {
    headers.set("Content-Type", "application/json");
  }
  if (options.csrfToken) {
    headers.set("X-CSRF-Token", options.csrfToken);
  }

  let response: Response;
  try {
    response = await fetch(`${dashboardApiBaseUrl()}${path}`, {
      method: options.method ?? "GET",
      headers,
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
      credentials: "include",
    });
  } catch {
    throw new DashboardApiError(0);
  }

  if (!response.ok) {
    throw new DashboardApiError(response.status);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  try {
    return (await response.json()) as T;
  } catch {
    throw new DashboardApiError(response.status);
  }
}
