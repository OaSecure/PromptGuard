import { getJson, postJson } from "./apiClient";
import { clearAuthState, getAuthState, saveAuthTokens } from "./authStore";
import type { ApiClientOptions } from "./apiClient";
import { isNormalizedError } from "../shared/errors";
import type { NormalizedError } from "../shared/types";

type AuthenticatedOptions = Omit<ApiClientOptions, "token">;

interface RefreshResponse {
  access_token: string;
  refresh_token?: string;
}

const unauthorizedError: NormalizedError = {
  code: "UNAUTHORIZED",
  message: "Login expired. Sign in again."
};

let refreshInFlight: Promise<RefreshResponse | NormalizedError> | undefined;

/** Sends an authenticated GET request and refreshes once after a 401. */
export async function getJsonWithAuthRefresh<TResponse>(path: string, options: AuthenticatedOptions): Promise<TResponse | NormalizedError> {
  return withAuthRefresh((token) => getJson<TResponse>(path, { ...options, token }), options);
}

/** Sends an authenticated JSON POST request and refreshes once after a 401. */
export async function postJsonWithAuthRefresh<TRequest, TResponse>(
  path: string,
  body: TRequest,
  options: AuthenticatedOptions
): Promise<TResponse | NormalizedError> {
  return withAuthRefresh((token) => postJson<TRequest, TResponse>(path, body, { ...options, token }), options);
}

async function withAuthRefresh<TResponse>(
  request: (token?: string) => Promise<TResponse | NormalizedError>,
  options: AuthenticatedOptions
): Promise<TResponse | NormalizedError> {
  const auth = await getAuthState();
  const first = await request(auth.accessToken);
  if (!isUnauthorized(first)) {
    return first;
  }
  if (!auth.refreshToken?.trim()) {
    return unauthorizedError;
  }

  const refreshed = await refreshAccessTokenSingleFlight(auth.refreshToken, options);
  if (isNormalizedError(refreshed)) {
    await clearAuthState();
    return unauthorizedError;
  }

  await saveAuthTokens({
    accessToken: refreshed.access_token,
    refreshToken: refreshed.refresh_token ?? auth.refreshToken
  });

  const retry = await request(refreshed.access_token);
  if (isUnauthorized(retry)) {
    await clearAuthState();
  }
  return retry;
}

async function refreshAccessToken(refreshToken: string, options: AuthenticatedOptions): Promise<RefreshResponse | NormalizedError> {
  const response = await postJson<{ refresh_token: string }, unknown>("/auth/refresh", { refresh_token: refreshToken }, options);
  if (isNormalizedError(response)) {
    return response;
  }
  if (!isRefreshResponse(response)) {
    return unauthorizedError;
  }
  return response;
}

/** Refreshes an access token through one shared in-flight request for concurrent real API calls. */
export function refreshAccessTokenSingleFlight(refreshToken: string, options: AuthenticatedOptions): Promise<RefreshResponse | NormalizedError> {
  if (!refreshInFlight) {
    refreshInFlight = refreshAccessToken(refreshToken, options).finally(() => {
      refreshInFlight = undefined;
    });
  }
  return refreshInFlight;
}

function isRefreshResponse(value: unknown): value is RefreshResponse {
  if (typeof value !== "object" || value === null) {
    return false;
  }
  const response = value as Partial<RefreshResponse>;
  return (
    typeof response.access_token === "string" &&
    response.access_token.trim().length > 0 &&
    (response.refresh_token === undefined || (typeof response.refresh_token === "string" && response.refresh_token.trim().length > 0))
  );
}

function isUnauthorized(value: unknown): value is NormalizedError {
  return isNormalizedError(value) && value.code === "UNAUTHORIZED";
}
