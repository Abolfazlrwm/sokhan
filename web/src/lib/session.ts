// Reactive view of the dashboard session for client components. The token
// itself lives in an httpOnly cookie the page cannot read, so the state
// comes from GET /auth/session (see api.ts) and is kept in sync across this
// tab (SESSION_CHANGE_EVENT) and other tabs (a BroadcastChannel).

import { useEffect, useSyncExternalStore } from "react";
import { useRouter } from "@/i18n/navigation";
import {
  SESSION_CHANGE_EVENT,
  getSessionState,
  getUnknownSessionState,
  loadSession,
} from "@/lib/api";

// Accounts created by the Telegram bot get a synthetic address that means
// nothing to the user, so it is not shown.
const SYNTHETIC_EMAIL_SUFFIX = "@telegram.sokhan.local";

function subscribe(onChange: () => void): () => void {
  window.addEventListener(SESSION_CHANGE_EVENT, onChange);
  if (getSessionState().status === "unknown") void loadSession();
  return () => window.removeEventListener(SESSION_CHANGE_EVENT, onChange);
}

export interface Session {
  /** False during SSR and until the API has said who is signed in. */
  ready: boolean;
  signedIn: boolean;
  /** The account email, or null when unknown or a Telegram placeholder. */
  email: string | null;
}

export function useSession(): Session {
  const state = useSyncExternalStore(subscribe, getSessionState, getUnknownSessionState);
  const email =
    state.email && !state.email.endsWith(SYNTHETIC_EMAIL_SUFFIX) ? state.email : null;
  return { ready: state.status !== "unknown", signedIn: state.status === "signedIn", email };
}

/** Send a signed-out visitor to the login page once the session is known. */
export function useRequireSignIn(): void {
  const { ready, signedIn } = useSession();
  const router = useRouter();
  useEffect(() => {
    if (ready && !signedIn) router.replace("/login");
  }, [ready, signedIn, router]);
}
