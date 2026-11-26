"use client";

import type { ReactNode } from "react";
import { Link } from "@/i18n/navigation";
import { useSession } from "@/lib/session";

/** The landing page's sign-in button; hidden once the visitor is signed in. */
export function LoginCta({ className, children }: { className: string; children: ReactNode }) {
  const { ready, signedIn } = useSession();
  if (!ready || signedIn) return null;
  return (
    <Link href="/login" className={className}>
      {children}
    </Link>
  );
}
