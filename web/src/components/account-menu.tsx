"use client";

import { useEffect, useId, useRef, useState } from "react";
import { useTranslations } from "next-intl";
import { ChevronDown, LogOut, UserRound } from "lucide-react";

/**
 * The signed-in account in the header: an avatar with the email's initial
 * that opens a small menu showing the full address and Sign out. The full
 * email no longer has to squeeze into the header row (where it was
 * truncated or hidden on narrow screens).
 */
export function AccountMenu({
  email,
  signingOut,
  onSignOut,
}: {
  email: string | null;
  signingOut: boolean;
  onSignOut: () => void;
}) {
  const t = useTranslations("nav");
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const signOutRef = useRef<HTMLButtonElement>(null);
  const menuId = useId();

  useEffect(() => {
    if (!open) return;
    signOutRef.current?.focus();

    function onPointerDown(event: PointerEvent) {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setOpen(false);
        buttonRef.current?.focus();
      }
    }
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  const initial = email ? email.charAt(0).toUpperCase() : null;

  return (
    <div ref={rootRef} className="relative">
      <button
        ref={buttonRef}
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? menuId : undefined}
        aria-label={email ? t("accountMenuFor", { email }) : t("accountMenu")}
        className="flex items-center gap-1 rounded-full p-0.5 text-stone-500 transition-colors hover:text-stone-800 focus-visible:ring-2 focus-visible:ring-teal-700 focus-visible:ring-offset-2"
      >
        <span
          className="flex h-9 w-9 items-center justify-center rounded-full bg-teal-100 text-sm font-bold text-teal-800"
          aria-hidden="true"
        >
          {initial ?? <UserRound className="h-5 w-5" />}
        </span>
        <ChevronDown
          className={`hidden h-4 w-4 transition-transform sm:block ${open ? "rotate-180" : ""}`}
          aria-hidden="true"
        />
      </button>

      {open ? (
        <div
          id={menuId}
          role="menu"
          aria-label={t("accountMenu")}
          className="absolute end-0 top-full z-50 mt-2 w-64 overflow-hidden rounded-xl border border-stone-200 bg-white shadow-lg"
        >
          <div className="border-b border-stone-100 px-4 py-3">
            <p className="text-xs text-stone-500">{email ? t("signedInLabel") : t("accountMenu")}</p>
            {email ? (
              <p
                dir="ltr"
                className="mt-0.5 break-all text-start text-sm font-medium text-stone-900"
              >
                {email}
              </p>
            ) : (
              <p className="mt-0.5 text-sm font-medium text-stone-900">{t("signedIn")}</p>
            )}
          </div>
          <button
            ref={signOutRef}
            type="button"
            role="menuitem"
            onClick={() => {
              setOpen(false);
              onSignOut();
            }}
            disabled={signingOut}
            className="flex w-full items-center gap-2 px-4 py-2.5 text-sm font-medium text-stone-700 transition-colors hover:bg-stone-50 hover:text-stone-900 focus-visible:bg-stone-50 focus-visible:outline-none disabled:opacity-60"
          >
            <LogOut className="h-4 w-4 rtl:-scale-x-100" aria-hidden="true" />
            {t("signOut")}
          </button>
        </div>
      ) : null}
    </div>
  );
}
