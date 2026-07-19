/**
 * Lightweight auth store backed by localStorage.
 * Stores the active bearer token and user metadata.
 * No framework — just module-level state + simple pub/sub so React
 * components can subscribe to changes.
 */

import type { StoredAuthUser } from './types';

const TOKEN_KEY = 'kandidly_token';
const USER_KEY  = 'kandidly_user';

type Listener = () => void;
const listeners = new Set<Listener>();

// Cached snapshots so useSyncExternalStore gets stable references.
let _cachedToken: string | null = localStorage.getItem(TOKEN_KEY);
let _cachedUser: StoredAuthUser | null = (() => {
  try {
    const raw = localStorage.getItem(USER_KEY);
    return raw ? (JSON.parse(raw) as StoredAuthUser) : null;
  } catch {
    return null;
  }
})();

function notify() {
  // Refresh caches before notifying subscribers.
  _cachedToken = localStorage.getItem(TOKEN_KEY);
  try {
    const raw = localStorage.getItem(USER_KEY);
    _cachedUser = raw ? (JSON.parse(raw) as StoredAuthUser) : null;
  } catch {
    _cachedUser = null;
  }
  listeners.forEach(fn => fn());
}

export function subscribeAuth(fn: Listener): () => void {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

export function getToken(): string | null {
  return _cachedToken;
}

export function getUser(): StoredAuthUser | null {
  return _cachedUser;
}

export function setAuth(user: StoredAuthUser): void {
  localStorage.setItem(TOKEN_KEY, user.token);
  localStorage.setItem(USER_KEY, JSON.stringify(user));
  notify();
}

export function clearAuth(): void {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
  notify();
}

export function isAdmin(): boolean {
  const user = getUser();
  return user?.role === 'admin' || user?.role === 'recruiter';
}

// Hardcoded on purpose (matches the backend gate, backend/app/domain/access.py)
// — one operator account owns the operator-only console surfaces (interview
// deletion, email smoke test, the console-access allowlist). The backend
// enforces this with 403s; the frontend only uses it to hide those surfaces.
export const OPERATOR_EMAIL = 'vishalkhare39@gmail.com';

export function isOperator(): boolean {
  return getUser()?.email?.toLowerCase() === OPERATOR_EMAIL;
}

export function isCandidate(): boolean {
  const user = getUser();
  return user?.role === 'candidate';
}
