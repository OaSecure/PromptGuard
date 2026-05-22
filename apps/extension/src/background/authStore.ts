import { STORAGE_KEYS } from "../shared/constants";

export interface AuthState {
  accessToken?: string;
}

export async function saveAccessToken(token: string): Promise<void> {
  const normalizedToken = token.trim();
  if (!normalizedToken) {
    await clearAuthState();
    return;
  }
  await chrome.storage.local.set({ [STORAGE_KEYS.accessToken]: normalizedToken });
}

export async function getAuthState(): Promise<AuthState> {
  const result = await chrome.storage.local.get(STORAGE_KEYS.accessToken);
  return { accessToken: result[STORAGE_KEYS.accessToken] };
}

export async function clearAuthState(): Promise<void> {
  await chrome.storage.local.remove([STORAGE_KEYS.accessToken, STORAGE_KEYS.refreshToken]);
}
