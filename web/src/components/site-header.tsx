"use client";

import { useLocale, useTranslations } from "next-intl";
import { AudioLines } from "lucide-react";
import { Link, usePathname, useRouter } from "@/i18n/navigation";

export function SiteHeader() {
  const t = useTranslations("nav");
  const locale = useLocale();
  const pathname = usePathname();
  const router = useRouter();

  const otherLocale = locale === "fa" ? "en" : "fa";

  const navItems = [
    { href: "/", label: t("home") },
    { href: "/new", label: t("new") },
    { href: "/jobs", label: t("archive") },
  ];

  return (
    <header className="sticky top-0 z-40 border-b border-stone-200 bg-white/90 backdrop-blur supports-[backdrop-filter]:bg-white/75">
      <div className="mx-auto flex h-16 w-full max-w-5xl items-center justify-between gap-4 px-4 sm:px-6">
        <Link
          href="/"
          className="flex items-center gap-2.5 rounded-lg focus-visible:ring-2 focus-visible:ring-teal-700 focus-visible:ring-offset-2"
        >
          <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-teal-700 text-white">
            <AudioLines className="h-5 w-5" aria-hidden="true" />
          </span>
          <span className="leading-tight">
            <span className="block text-lg font-bold text-stone-900">{t("brand")}</span>
            <span className="block text-xs text-stone-500">{t("brandTagline")}</span>
          </span>
        </Link>

        <nav aria-label={t("navLabel")} className="flex items-center gap-1 sm:gap-2">
          {navItems.map((item) => {
            const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                aria-current={active ? "page" : undefined}
                className={`rounded-lg px-2 py-2 text-sm font-medium transition-colors focus-visible:ring-2 focus-visible:ring-teal-700 sm:px-3 ${
                  active
                    ? "bg-teal-50 text-teal-800"
                    : "text-stone-600 hover:bg-stone-100 hover:text-stone-900"
                }`}
              >
                {item.label}
              </Link>
            );
          })}
          <button
            type="button"
            onClick={() => router.replace(pathname, { locale: otherLocale })}
            aria-label={otherLocale === "en" ? t("switchToEn") : t("switchToFa")}
            className="rounded-lg border border-stone-300 px-3 py-2 text-sm font-medium text-stone-700 transition-colors hover:border-teal-700 hover:text-teal-800 focus-visible:ring-2 focus-visible:ring-teal-700"
          >
            {otherLocale === "en" ? "EN" : "فا"}
          </button>
        </nav>
      </div>
    </header>
  );
}
