/**
 * Google reCAPTCHA v3 loader + executor.
 *
 * v3 is invisible (no widget): we load the script once for a given site key,
 * then mint a short-lived token bound to an `action` right before a protected
 * request. The token goes to the backend in the `X-Recaptcha-Token` header,
 * where app/core/captcha.py verifies it via siteverify.
 *
 * When `siteKey` is empty (reCAPTCHA not configured — e.g. local dev) every
 * function is a no-op that resolves to `null`, so the caller sends no token and
 * the fail-open backend skips verification.
 */

interface Grecaptcha {
  ready: (cb: () => void) => void;
  execute: (siteKey: string, opts: { action: string }) => Promise<string>;
}

declare global {
  interface Window {
    grecaptcha?: Grecaptcha;
  }
}

let loadPromise: Promise<void> | null = null;

/** Inject the reCAPTCHA v3 script once and resolve when it's ready. */
export function loadRecaptcha(siteKey: string): Promise<void> {
  if (!siteKey) return Promise.resolve();
  if (loadPromise) return loadPromise;

  loadPromise = new Promise<void>((resolve, reject) => {
    if (window.grecaptcha) {
      resolve();
      return;
    }
    const script = document.createElement('script');
    script.src = `https://www.google.com/recaptcha/api.js?render=${encodeURIComponent(siteKey)}`;
    script.async = true;
    script.defer = true;
    script.onload = () => resolve();
    script.onerror = () => {
      loadPromise = null; // allow a later retry
      reject(new Error('Failed to load reCAPTCHA'));
    };
    document.head.appendChild(script);
  });
  return loadPromise;
}

/**
 * Mint a fresh v3 token for `action`. Returns `null` when reCAPTCHA is not
 * configured or the script is unavailable so callers can proceed unchallenged.
 */
export async function executeRecaptcha(
  siteKey: string,
  action: string,
): Promise<string | null> {
  if (!siteKey) return null;
  await loadRecaptcha(siteKey);
  const g = window.grecaptcha;
  if (!g) return null;
  await new Promise<void>(res => g.ready(() => res()));
  return g.execute(siteKey, { action });
}
