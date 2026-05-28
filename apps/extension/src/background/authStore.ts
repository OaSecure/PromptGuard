import { STORAGE_KEYS } from "../shared/constants";

/** Authentication state available to background API clients. */
export interface AuthState {
  accessToken?: string;
  refreshToken?: string;
}

/**
 * Stores a bearer token for real API mode.
 *
 * Blank writes clear auth state so the options page can remove stale
 * credentials without a separate reset path.
 */
export async function saveAccessToken(token: string): Promise<void> {
  await saveAuthTokens({ accessToken: token });
}

/** Stores access and optional refresh tokens for real API mode. */
export async function saveAuthTokens(tokens: AuthState): Promise<void> {
  const normalizedToken = tokens.accessToken?.trim() ?? "";
  if (!normalizedToken) {
    await clearAuthState();
    return;
  }
  const entries: Record<string, string> = { [STORAGE_KEYS.accessToken]: normalizedToken };
  const normalizedRefreshToken = tokens.refreshToken?.trim();
  if (normalizedRefreshToken) {
    entries[STORAGE_KEYS.refreshToken] = normalizedRefreshToken;
  }
  await chrome.storage.local.set(entries);
}

/** Reads the current auth tokens from extension-local storage. */
export async function getAuthState(): Promise<AuthState> {
  const result = await chrome.storage.local.get([STORAGE_KEYS.accessToken, STORAGE_KEYS.refreshToken]);
  return {
    accessToken: typeof result[STORAGE_KEYS.accessToken] === "string" ? result[STORAGE_KEYS.accessToken] : undefined,
    refreshToken: typeof result[STORAGE_KEYS.refreshToken] === "string" ? result[STORAGE_KEYS.refreshToken] : undefined
  };
}

/** Removes stored access and refresh tokens from extension-local storage. */
export async function clearAuthState(): Promise<void> {
  await chrome.storage.local.remove([STORAGE_KEYS.accessToken, STORAGE_KEYS.refreshToken]);
}
