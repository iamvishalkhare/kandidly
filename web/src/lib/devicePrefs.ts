/**
 * Persisted camera/mic choices from the lobby device check, consumed when the
 * interview room publishes the mic and starts the proctoring snapshot loop.
 * localStorage (not router state) so a mid-interview refresh keeps the choice.
 */

export type DeviceKind = 'audioinput' | 'videoinput';

const KEY: Record<DeviceKind, string> = {
  audioinput: 'kandidly:device:audioinput',
  videoinput: 'kandidly:device:videoinput',
};

export function getPreferredDevice(kind: DeviceKind): string | null {
  try {
    return localStorage.getItem(KEY[kind]);
  } catch {
    return null;
  }
}

export function setPreferredDevice(kind: DeviceKind, deviceId: string | null): void {
  try {
    if (deviceId) localStorage.setItem(KEY[kind], deviceId);
    else localStorage.removeItem(KEY[kind]);
  } catch {
    /* private mode etc. — the preference just won't stick */
  }
}
