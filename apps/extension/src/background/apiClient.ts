import { DEFAULT_TIMEOUT_MS } from "../shared/constants";
import { normalizeError } from "../shared/errors";
import type { NormalizedError } from "../shared/types";

export interface ApiClientOptions {
  baseUrl: string;
  token?: string;
  timeoutMs?: number;
}

export async function postJson<TRequest, TResponse>(path: string, body: TRequest, options: ApiClientOptions): Promise<TResponse | NormalizedError> {
  const controller = new AbortController();
  const timeout = globalThis.setTimeout(() => controller.abort(), options.timeoutMs ?? DEFAULT_TIMEOUT_MS);

  try {
    const response = await fetch(apiUrl(options.baseUrl, path), {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-PromptGuard-Client": "chrome-extension",
        "X-PromptGuard-Extension-Version": "0.4.0",
        ...(options.token ? { Authorization: `Bearer ${options.token}` } : {})
      },
      body: JSON.stringify(body),
      signal: controller.signal
    });

    if (!response.ok) {
      return errorFromStatus(response.status);
    }

    return (await response.json()) as TResponse;
  } catch (error) {
    return normalizeError(error);
  } finally {
    globalThis.clearTimeout(timeout);
  }
}

export async function getJson<TResponse>(path: string, options: ApiClientOptions): Promise<TResponse | NormalizedError> {
  const controller = new AbortController();
  const timeout = globalThis.setTimeout(() => controller.abort(), options.timeoutMs ?? DEFAULT_TIMEOUT_MS);

  try {
    const response = await fetch(apiUrl(options.baseUrl, path), {
      method: "GET",
      headers: {
        "X-PromptGuard-Client": "chrome-extension",
        "X-PromptGuard-Extension-Version": "0.4.0",
        ...(options.token ? { Authorization: `Bearer ${options.token}` } : {})
      },
      signal: controller.signal
    });

    if (!response.ok) {
      return errorFromStatus(response.status);
    }

    return (await response.json()) as TResponse;
  } catch (error) {
    return normalizeError(error);
  } finally {
    globalThis.clearTimeout(timeout);
  }
}

export function apiUrl(baseUrl: string, path: string): string {
  const normalizedBase = baseUrl.replace(/\/+$/, "");
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  return `${normalizedBase}${normalizedPath}`;
}

function errorFromStatus(status: number): NormalizedError {
  if (status === 401) {
    return { code: "UNAUTHORIZED", message: "Login expired. Sign in again." };
  }
  if (status >= 500) {
    return { code: "SERVER_ERROR", message: "Server error prevented inspection." };
  }
  return { code: "VALIDATION_ERROR", message: "Request could not be processed." };
}
