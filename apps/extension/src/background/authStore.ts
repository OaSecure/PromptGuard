import { STORAGE_KEYS } from "../shared/constants";

/** Authentication state available to background API clients. */
export interface AuthState {
  accessToken?: string;
}

/**
 * Stores a bearer token for real API mode.
 *
 * Blank writes clear auth state so the options page can remove stale
 * credentials without a separate reset path.
 */
export async function saveAccessToken(token: string): Promise<void> {
  const normalizedToken = token.trim();
  if (!normalizedToken) {
    await clearAuthState();
    return;
  }
  await chrome.storage.local.set({ [STORAGE_KEYS.accessToken]: normalizedToken });
}

/** Reads the current bearer token from extension-local storage. */
export async function getAuthState(): Promise<AuthState> {
  const result = await chrome.storage.local.get(STORAGE_KEYS.accessToken);
  return { accessToken: result[STORAGE_KEYS.accessToken] };
}

/** Removes stored access and refresh tokens from extension-local storage. */
export async function clearAuthState(): Promise<void> {
  await chrome.storage.local.remove([STORAGE_KEYS.accessToken, STORAGE_KEYS.refreshToken]);
}
