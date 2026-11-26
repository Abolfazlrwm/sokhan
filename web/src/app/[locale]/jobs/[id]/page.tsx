"use client";

import { useEffect, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { useParams } from "next/navigation";
import { ArrowRight, Check, Copy, Download, FileText, Trash2 } from "lucide-react";
import { Link, useRouter } from "@/i18n/navigation";
import {
  ApiError,
  deleteJob,
  downloadTranscript,
  getJob,
  type JobDetail,
  type TranscriptFormat,
} from "@/lib/api";
import { useRequireSignIn } from "@/lib/session";
import { ProgressBar, StatusBadge } from "@/components/job-bits";

const POLL_INTERVAL_MS = 3000;

const DOWNLOAD_FORMATS: TranscriptFormat[] = ["txt", "srt", "vtt", "json", "docx"];

// Mirrors the backend's LOW_CONFIDENCE_THRESHOLD default: segments the
// engine was unsure about get a "needs review" badge in the timeline.
const LOW_CONFIDENCE_THRESHOLD = 0.5;

function formatTimestamp(seconds: number): string {
  const total = Math.max(0, Math.floor(seconds));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const secs = total % 60;
  const mm = String(minutes).padStart(2, "0");
  const ss = String(secs).padStart(2, "0");
  return hours > 0 ? `${hours}:${mm}:${ss}` : `${mm}:${ss}`;
}

function formatSeconds(total: number, locale: string): string {
  const minutes = Math.round(total / 60);
  return new Intl.NumberFormat(locale, {
    style: "unit",
    unit: "minute",
    unitDisplay: "long",
  }).format(Math.max(1, minutes));
}

function formatDate(iso: string | null, locale: string): string {
  if (!iso) return "—";
  try {
    return new Intl.DateTimeFormat(locale, {
      dateStyle: "medium",
      timeStyle: "short",
    }).format(new Date(iso));
  } catch {
    return "—";
  }
}

function formatTimestampLabel(format: TranscriptFormat, t: (key: string) => string): string {
  if (format === "txt") return t("downloadTxt");
  if (format === "srt") return t("downloadSrt");
  if (format === "vtt") return t("downloadVtt");
  if (format === "json") return t("downloadJson");
  return t("downloadDocx");
}

export default function JobDetailPage() {
  const { id: jobId } = useParams<{ id: string }>();
  const locale = useLocale();
  const t = useTranslations("jobDetail");
  const tc = useTranslations("common");
  const te = useTranslations("errors");
  const router = useRouter();

  const [job, setJob] = useState<JobDetail | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [missing, setMissing] = useState(false);
  const [pendingFormat, setPendingFormat] = useState<TranscriptFormat | null>(null);
  const [downloadError, setDownloadError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  useRequireSignIn();

  useEffect(() => {
    let active = true;
    let timer: ReturnType<typeof setTimeout> | undefined;

    async function poll() {
      try {
        const data = await getJob(jobId);
        if (!active) return;
        setJob(data);
        setLoadError(null);
        if (data.status === "queued" || data.status === "processing") {
          timer = setTimeout(poll, POLL_INTERVAL_MS);
        }
      } catch (error) {
        if (!active) return;
        if (error instanceof ApiError) {
          if (error.status === 401) return; // the api client already redirects
          if (error.status === 404) {
            setMissing(true);
            return;
          }
          setLoadError(error.status === 0 ? te("network") : te("generic"));
        } else {
          setLoadError(te("network"));
        }
        timer = setTimeout(poll, POLL_INTERVAL_MS);
      }
    }

    poll();
    return () => {
      active = false;
      if (timer) clearTimeout(timer);
    };
  }, [jobId, router, te]);

  async function handleDownload(format: TranscriptFormat) {
    setPendingFormat(format);
    setDownloadError(null);
    try {
      const blob = await downloadTranscript(jobId, format);
      const baseName = (job?.filename ?? "sokhan-transcript").replace(/\.[^.]+$/, "");
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `${baseName}.${format}`;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
    } catch {
      setDownloadError(t("downloadError"));
    } finally {
      setPendingFormat(null);
    }
  }

  async function handleCopy() {
    if (!job?.text) return;
    try {
      await navigator.clipboard.writeText(job.text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      setDownloadError(t("copyFailed"));
    }
  }

  async function handleDelete() {
    if (!window.confirm(t("deleteConfirm"))) return;
    setDeleting(true);
    setDeleteError(null);
    try {
      await deleteJob(jobId);
      router.push("/jobs");
    } catch {
      setDeleteError(t("deleteError"));
      setDeleting(false);
    }
  }

  function languageLabel(language: string): string {
    if (language === "fa") return t("languageFa");
    if (language === "en") return t("languageEn");
    if (language === "auto") return t("languageAuto");
    return language;
  }

  const isPending = job !== null && (job.status === "queued" || job.status === "processing");

  return (
    <div className="mx-auto w-full max-w-3xl px-4 py-10 sm:px-6 sm:py-14">
      <Link
        href="/jobs"
        className="inline-flex items-center gap-1.5 text-sm font-medium text-stone-600 transition-colors hover:text-teal-800"
      >
        <ArrowRight className="h-4 w-4 rtl:-scale-x-100" aria-hidden="true" />
        {t("back")}
      </Link>

      {missing ? (
        <div className="mt-8 rounded-xl border border-dashed border-stone-300 bg-white p-10 text-center">
          <h1 className="font-bold text-stone-900">{te("notFound")}</h1>
        </div>
      ) : null}

      {loadError && !missing ? (
        <div
          role="alert"
          className="mt-8 rounded-xl border border-red-200 bg-red-50 p-4 text-sm leading-7 text-red-800"
        >
          {loadError}
        </div>
      ) : null}

      {!job && !missing && !loadError ? (
        <div className="mt-16 flex justify-center">
          <span
            className="h-8 w-8 animate-spin rounded-full border-2 border-stone-300 border-t-teal-700"
            aria-hidden="true"
          />
          <span className="sr-only">{tc("loading")}</span>
        </div>
      ) : null}

      {job ? (
        <div className="mt-6 space-y-5">
          <div className="rounded-xl border border-stone-200 bg-white p-5 shadow-sm sm:p-6">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="flex min-w-0 items-center gap-3">
                <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-teal-50 text-teal-700">
                  <FileText className="h-5 w-5" aria-hidden="true" />
                </span>
                <div className="min-w-0">
                  <h1 dir="auto" className="truncate text-lg font-bold text-stone-900">
                    {job.filename}
                  </h1>
                </div>
              </div>
              <div className="flex items-center gap-3">
                <StatusBadge status={job.status} />
                <button
                  type="button"
                  onClick={handleDelete}
                  disabled={deleting}
                  className="inline-flex min-h-9 items-center gap-1.5 rounded-lg border border-red-200 px-3 text-xs font-bold text-red-700 transition-colors hover:border-red-700 hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
                  {deleting ? t("deletePending") : t("deleteJob")}
                </button>
              </div>
            </div>
            <dl className="mt-5 grid grid-cols-2 gap-4 text-sm sm:grid-cols-4">
              <div>
                <dt className="text-xs text-stone-500">{t("metaDuration")}</dt>
                <dd className="mt-1 font-bold text-stone-800">
                  {job.duration_seconds > 0
                    ? formatSeconds(job.duration_seconds, locale)
                    : "—"}
                </dd>
              </div>
              <div>
                <dt className="text-xs text-stone-500">{t("metaLanguage")}</dt>
                <dd className="mt-1 font-bold text-stone-800">{languageLabel(job.language)}</dd>
              </div>
              <div>
                <dt className="text-xs text-stone-500">{t("metaCreated")}</dt>
                <dd className="mt-1 font-bold text-stone-800">
                  {formatDate(job.created_at, locale)}
                </dd>
              </div>
              <div>
                <dt className="text-xs text-stone-500">{t("metaCompleted")}</dt>
                <dd className="mt-1 font-bold text-stone-800">
                  {formatDate(job.completed_at, locale)}
                </dd>
              </div>
            </dl>
            {deleteError ? (
              <p role="alert" className="mt-3 text-sm text-red-700">
                {deleteError}
              </p>
            ) : null}
          </div>

          {isPending ? (
            <div className="rounded-xl border border-stone-200 bg-white p-5 shadow-sm sm:p-6">
              <h2 className="font-bold text-stone-900">{t("processingTitle")}</h2>
              <p className="mt-1.5 text-sm leading-7 text-stone-600">{t("processingDesc")}</p>
              <div className="mt-4">
                <ProgressBar value={job.progress} label={t("metaDuration")} />
                <p className="mt-1.5 text-xs text-stone-500">
                  {new Intl.NumberFormat(locale).format(
                    Math.min(100, Math.max(0, Math.round(job.progress))),
                  )}
                  ٪
                </p>
              </div>
            </div>
          ) : null}

          {job.status === "failed" ? (
            <div
              role="alert"
              className="rounded-xl border border-red-200 bg-red-50 p-5 sm:p-6"
            >
              <h2 className="font-bold text-red-900">{t("failedTitle")}</h2>
              <p className="mt-1.5 text-sm leading-7 text-red-800">{t("failedDesc")}</p>
              {job.error ? (
                <p className="mt-3 text-xs leading-6 text-red-700/80">{job.error}</p>
              ) : null}
            </div>
          ) : null}

          {job.status === "completed" && job.summary ? (
            <div className="rounded-xl border border-teal-200 bg-teal-50 p-5 sm:p-6">
              <h2 className="font-bold text-teal-900">{t("summaryTitle")}</h2>
              <p className="mt-2 whitespace-pre-wrap text-sm leading-8 text-teal-950">
                {job.summary}
              </p>
            </div>
          ) : null}

          {job.status === "completed" && job.text ? (
            <div className="rounded-xl border border-stone-200 bg-white p-5 shadow-sm sm:p-6">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <h2 className="font-bold text-stone-900">{t("transcriptTitle")}</h2>
                <button
                  type="button"
                  onClick={handleCopy}
                  className="inline-flex min-h-9 items-center gap-1.5 rounded-lg border border-stone-300 px-3 text-xs font-bold text-stone-700 transition-colors hover:border-teal-700 hover:text-teal-800"
                >
                  {copied ? (
                    <Check className="h-3.5 w-3.5" aria-hidden="true" />
                  ) : (
                    <Copy className="h-3.5 w-3.5" aria-hidden="true" />
                  )}
                  {copied ? t("copied") : t("copyTranscript")}
                </button>
              </div>
              {job.segments && job.segments.length > 0 ? (
                <ol className="mt-4 space-y-2.5">
                  {job.segments.map((segment) => (
                    <li
                      key={segment.position}
                      className="flex flex-wrap items-baseline gap-x-3 gap-y-1 rounded-lg bg-stone-50 px-3 py-2.5"
                    >
                      <span
                        dir="ltr"
                        className="shrink-0 rounded-md bg-stone-200 px-2 py-0.5 font-mono text-xs text-stone-700"
                      >
                        {formatTimestamp(segment.start)} → {formatTimestamp(segment.end)}
                      </span>
                      {segment.speaker ? (
                        <span className="rounded-full bg-teal-50 px-2 py-0.5 text-xs font-bold text-teal-800">
                          {segment.speaker}
                        </span>
                      ) : null}
                      {segment.confidence !== null &&
                      segment.confidence < LOW_CONFIDENCE_THRESHOLD ? (
                        <span
                          title={t("confidencePercent", {
                            percent: Math.round(segment.confidence * 100),
                          })}
                          className="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-bold text-amber-800"
                        >
                          {t("lowConfidence")}
                        </span>
                      ) : null}
                      <p
                        dir="auto"
                        className="min-w-0 flex-1 text-[15px] leading-8 text-stone-800"
                      >
                        {segment.text}
                      </p>
                    </li>
                  ))}
                </ol>
              ) : (
                <p
                  dir="auto"
                  className="mt-3 whitespace-pre-wrap text-[15px] leading-9 text-stone-800"
                >
                  {job.text}
                </p>
              )}
            </div>
          ) : null}

          {job.status === "completed" ? (
            <div className="rounded-xl border border-stone-200 bg-white p-5 shadow-sm sm:p-6">
              <h2 className="font-bold text-stone-900">{t("downloadTitle")}</h2>
              <div className="mt-4 flex flex-wrap gap-3">
                {DOWNLOAD_FORMATS.map((format) => (
                  <button
                    key={format}
                    type="button"
                    onClick={() => handleDownload(format)}
                    disabled={pendingFormat !== null}
                    className="inline-flex min-h-11 items-center gap-2 rounded-xl border border-stone-300 bg-white px-5 text-sm font-bold text-stone-800 transition-colors hover:border-teal-700 hover:text-teal-800 focus-visible:ring-2 focus-visible:ring-teal-700 focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    {pendingFormat === format ? (
                      <>
                        <span
                          className="h-4 w-4 animate-spin rounded-full border-2 border-stone-300 border-t-teal-700"
                          aria-hidden="true"
                        />
                        {t("downloadPending")}
                      </>
                    ) : (
                      <>
                        <Download className="h-4 w-4" aria-hidden="true" />
                        {formatTimestampLabel(format, t)}
                      </>
                    )}
                  </button>
                ))}
              </div>
              {downloadError ? (
                <p role="alert" className="mt-3 text-sm text-red-700">
                  {downloadError}
                </p>
              ) : null}
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
