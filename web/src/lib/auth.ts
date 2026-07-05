/**
 * Lightweight auth store backed by localStorage.
 * Stores the active bearer token and user metadata.
 * No framework — just module-level state + simple pub/sub so React
 * components can subscribe to changes.
 */

import type { DevUser } from './types';

const TOKEN_KEY = 'kandidly_token';
const USER_KEY  = 'kandidly_user';

type Listener = () => void;
const listeners = new Set<Listener>();

// Cached snapshots so useSyncExternalStore gets stable references.
let _cachedToken: string | null = localStorage.getItem(TOKEN_KEY);
let _cachedUser: DevUser | null = (() => {
  try {
    const raw = localStorage.getItem(USER_KEY);
    return raw ? (JSON.parse(raw) as DevUser) : null;
  } catch {
    return null;
  }
})();

function notify() {
  // Refresh caches before notifying subscribers.
  _cachedToken = localStorage.getItem(TOKEN_KEY);
  try {
    const raw = localStorage.getItem(USER_KEY);
    _cachedUser = raw ? (JSON.parse(raw) as DevUser) : null;
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

export function getUser(): DevUser | null {
  return _cachedUser;
}

export function setAuth(user: DevUser): void {
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

export function isCandidate(): boolean {
  const user = getUser();
  return user?.role === 'candidate';
}
