const STORAGE_KEY = "dashboardApiKey";

export function getApiKey(): string {
  try {
    return localStorage.getItem(STORAGE_KEY) ?? "";
  } catch {
    return "";
  }
}

export function setApiKey(key: string): void {
  try {
    localStorage.setItem(STORAGE_KEY, key);
  } catch {
    // localStorage may be unavailable (private browsing, disabled storage) — ignore.
  }
}

export function clearApiKey(): void {
  try {
    localStorage.removeItem(STORAGE_KEY);
  } catch {
    // ignore, see setApiKey
  }
}

export class UnauthorizedError extends Error {
  constructor() {
    super("Unauthorized");
  }
}

export async function authFetch(url: string, options: RequestInit = {}): Promise<Response> {
  const headers = new Headers(options.headers);
  headers.set("X-API-Key", getApiKey());
  const response = await fetch(url, { ...options, headers });
  if (response.status === 401) {
    throw new UnauthorizedError();
  }
  return response;
}
