"use client";

import { useCallback, useSyncExternalStore } from "react";

const EVENT = "focos:storage";

function subscribe(cb: () => void) {
  window.addEventListener("storage", cb);
  window.addEventListener(EVENT, cb);
  return () => {
    window.removeEventListener("storage", cb);
    window.removeEventListener(EVENT, cb);
  };
}

/**
 * A localStorage value that is null on the server and during hydration,
 * then the stored string (or "" when unset) on the client.
 */
export function useLocalStorage(key: string): [string | null, (v: string | null) => void] {
  const value = useSyncExternalStore(
    subscribe,
    () => window.localStorage.getItem(key) ?? "",
    () => null,
  );
  const set = useCallback(
    (v: string | null) => {
      if (v == null || v === "") window.localStorage.removeItem(key);
      else window.localStorage.setItem(key, v);
      window.dispatchEvent(new Event(EVENT));
    },
    [key],
  );
  return [value, set];
}
