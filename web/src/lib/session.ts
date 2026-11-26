// Reactive view of the stored session for client components. The token
// lives in localStorage (see api.ts); this hook re-renders on sign-in and
// sign-out in this tab (SESSION_CHANGE_EVENT) and in other tabs ("storage").

import { useSyncExternalStore } from "react";
import { SESSION_CHANGE_EVENT, getEmail, getToken } from "@/lib/api";

// Accounts created by the Telegram bot get a synthetic address that means
// nothing to the user, so it is not shown.
const SYNTHETIC_EMAIL_SUFFIX = "@telegram.sokhan.local";

function subscribe(onChange: () => void): () => void {
  window.addEventListener("storage", onChange);
  window.addEventListener(SESSION_CHANGE_EVENT, onChange);
  return () => {
    window.removeEventListener("storage", onChange);
    window.removeEventListener(SESSION_CHANGE_EVENT, onChange);
  };
}

const onServer = () => false;

export interface Session {
  /** False during SSR and the first client render, before storage is readable. */
  ready: boolean;
  signedIn: boolean;
  /** The account email, or null when unknown or a Telegram placeholder. */
  email: string | null;
}

export function useSession(): Session {
  const ready = useSyncExternalStore(subscribe, () => true, onServer);
  const signedIn = useSyncExternalStore(subscribe, () => getToken() !== null, onServer);
  const storedEmail = useSyncExternalStore(subscribe, getEmail, () => null);
  const email = storedEmail && !storedEmail.endsWith(SYNTHETIC_EMAIL_SUFFIX) ? storedEmail : null;
  return { ready, signedIn, email };
}
