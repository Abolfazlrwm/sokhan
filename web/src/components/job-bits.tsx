"use client";

import { useTranslations } from "next-intl";
import type { JobStatus } from "@/lib/api";

const badgeStyles: Record<JobStatus, string> = {
  queued: "bg-amber-100 text-amber-800",
  processing: "bg-teal-100 text-teal-800",
  completed: "bg-emerald-100 text-emerald-800",
  failed: "bg-red-100 text-red-800",
};

const statusKeys: Record<JobStatus, string> = {
  queued: "statusQueued",
  processing: "statusProcessing",
  completed: "statusCompleted",
  failed: "statusFailed",
};

export function StatusBadge({ status }: { status: JobStatus }) {
  const t = useTranslations("jobs");

  return (
    <span
      className={`inline-flex items-center gap-1.5 whitespace-nowrap rounded-full px-2.5 py-1 text-xs font-bold ${
        badgeStyles[status]
      }`}
    >
      {status === "processing" ? (
        <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-current" aria-hidden="true" />
      ) : null}
      {t(statusKeys[status])}
    </span>
  );
}

export function ProgressBar({ value, label }: { value: number; label?: string }) {
  const clamped = Math.min(100, Math.max(0, value));

  return (
    <div
      className="h-2 w-full overflow-hidden rounded-full bg-stone-100"
      role="progressbar"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={Math.round(clamped)}
      aria-label={label}
    >
      <div
        className="h-full rounded-full bg-teal-700 transition-[width] duration-500 ease-out"
        style={{ width: `${clamped}%` }}
      />
    </div>
  );
}
