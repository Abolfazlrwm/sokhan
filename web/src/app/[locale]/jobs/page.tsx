"use client";

import { useEffect, useRef, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { Clock, Search } from "lucide-react";
import { Link, useRouter } from "@/i18n/navigation";
import {
  ApiError,
  getToken,
  listJobs,
  searchJobs,
  type JobListItem,
} from "@/lib/api";
import { ProgressBar, StatusBadge } from "@/components/job-bits";

function formatDate(iso: string, locale: string): string {
  try {
    return new Intl.DateTimeFormat(locale, {
      dateStyle: "medium",
      timeStyle: "short",
    }).format(new Date(iso));
  } catch {
    return "—";
  }
}

export default function JobsPage() {
  const t = useTranslations("jobs");
  const tc = useTranslations("common");
  const te = useTranslations("errors");
  const locale = useLocale();
  const router = useRouter();
  const nf = new Intl.NumberFormat(locale);

  const [query, setQuery] = useState("");
  const [items, setItems] = useState<JobListItem[] | null>(null);
  const [listError, setListError] = useState<string | null>(null);

  useEffect(() => {
    if (!getToken()) router.replace("/login");
  }, [router]);

  const seqRef = useRef(0);
  useEffect(() => {
    let cancelled = false;
    const timer = setTimeout(
      async () => {
        const seq = ++seqRef.current;
        try {
          const trimmed = query.trim();
          const data = trimmed ? await searchJobs(trimmed) : await listJobs();
          if (!cancelled && seq === seqRef.current) {
            setItems(data.items);
            setListError(null);
          }
        } catch (error) {
          if (!cancelled && error instanceof ApiError && error.status !== 401) {
            setListError(
              error.status === 0
                ? te("network")
                : error.status === 404
                  ? te("notFound")
                  : te("generic"),
            );
          }
        }
      },
      query.trim() ? 300 : 0,
    );

    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [query]);

  const hasQuery = query.trim().length > 0;

  return (
    <div className="mx-auto w-full max-w-5xl px-4 py-10 sm:px-6 sm:py-14">
      <header className="mb-8">
        <h1 className="text-2xl font-bold text-stone-900 sm:text-3xl">{t("title")}</h1>
        <p className="mt-2 text-sm leading-7 text-stone-600">{t("subtitle")}</p>
      </header>

      <div className="relative">
        <label htmlFor="job-search" className="sr-only">
          {t("searchLabel")}
        </label>
        <Search
          className="pointer-events-none absolute start-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-stone-400"
          aria-hidden="true"
        />
        <input
          id="job-search"
          type="search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder={t("searchPlaceholder")}
          className="h-11 w-full rounded-xl border border-stone-300 bg-white ps-10 pe-4 text-base text-stone-900 placeholder:text-stone-400 focus:border-teal-600 focus:outline-none focus:ring-2 focus:ring-teal-600/20 sm:text-sm"
        />
      </div>

      {listError ? (
        <div
          role="alert"
          className="mt-6 rounded-xl border border-red-200 bg-red-50 p-4 text-sm leading-7 text-red-800"
        >
          {listError}
        </div>
      ) : null}

      {!items && !listError ? (
        <div className="mt-16 flex justify-center">
          <span
            className="h-8 w-8 animate-spin rounded-full border-2 border-stone-300 border-t-teal-700"
            aria-hidden="true"
          />
          <span className="sr-only">{tc("loading")}</span>
        </div>
      ) : null}

      {items && items.length === 0 && !hasQuery ? (
        <div className="mt-10 rounded-xl border border-dashed border-stone-300 bg-white p-10 text-center">
          <h2 className="font-bold text-stone-900">{t("emptyTitle")}</h2>
          <p className="mt-2 text-sm leading-7 text-stone-600">{t("emptyDesc")}</p>
          <Link
            href="/new"
            className="mt-5 inline-flex min-h-11 items-center rounded-xl bg-teal-700 px-5 text-sm font-bold text-white shadow-sm transition-colors hover:bg-teal-600 focus-visible:ring-2 focus-visible:ring-teal-700 focus-visible:ring-offset-2"
          >
            {t("emptyCta")}
          </Link>
        </div>
      ) : null}

      {items && items.length === 0 && hasQuery ? (
        <div className="mt-10 rounded-xl border border-dashed border-stone-300 bg-white p-10 text-center">
          <h2 className="font-bold text-stone-900">{t("noResultsTitle")}</h2>
          <p className="mt-2 text-sm leading-7 text-stone-600">{t("noResultsDesc")}</p>
        </div>
      ) : null}

      {items && items.length > 0 ? (
        <ul className="mt-6 space-y-3">
          {items.map((job) => (
            <li key={job.id}>
              <Link
                href={`/jobs/${job.id}`}
                className="block rounded-xl border border-stone-200 bg-white p-4 shadow-sm transition-all hover:border-teal-700/40 hover:shadow-md focus-visible:ring-2 focus-visible:ring-teal-700 sm:p-5"
              >
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0 flex-1">
                    <p dir="auto" className="truncate font-bold text-stone-900">
                      {job.filename}
                    </p>
                    <p className="mt-1 text-xs text-stone-500">
                      {formatDate(job.created_at, locale)}
                    </p>
                  </div>
                  <div className="flex shrink-0 items-center gap-2 sm:gap-3">
                    <span className="inline-flex items-center gap-1.5 text-sm text-stone-600">
                      <Clock className="h-4 w-4 text-stone-400" aria-hidden="true" />
                      {job.duration_seconds > 0
                        ? tc("minutes", {
                            count: nf.format(Math.max(1, Math.round(job.duration_seconds / 60))),
                          })
                        : "—"}
                    </span>
                    <StatusBadge status={job.status} />
                  </div>
                </div>
                {job.status === "processing" ? (
                  <div className="mt-4">
                    <ProgressBar value={job.progress} label={t("progressLabel")} />
                    <p className="mt-1.5 text-xs text-stone-500">
                      {t("percent", {
                        value: nf.format(Math.min(100, Math.max(0, job.progress))),
                      })}
                    </p>
                  </div>
                ) : null}
              </Link>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
