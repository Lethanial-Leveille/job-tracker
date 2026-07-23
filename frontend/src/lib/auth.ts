// Token storage for the logged-in session. The JWT lives in localStorage under
// one key. localStorage is the simplest choice for a single-user app; the safer
// httpOnly-cookie approach is a documented future upgrade (it defends against a
// class of script-injection attacks but needs more CORS/server setup).

const TOKEN_KEY = "scout_auth_token";

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY);
}
