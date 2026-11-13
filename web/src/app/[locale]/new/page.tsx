"use client";

import { useEffect, useRef, useState, type DragEvent, type FormEvent } from "react";
import { useLocale, useTranslations } from "next-intl";
import { ChevronDown, FileText, Mic, Square, Upload } from "lucide-react";
import { useRouter } from "@/i18n/navigation";
import { ApiError, getQuota, getToken, uploadJob, type QuotaInfo } from "@/lib/api";

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  const kib = bytes / 1024;
  if (kib < 1024) return `${kib.toFixed(1)} KB`;
  return `${(kib / 1024).toFixed(1)} MB`;
}

function formatClock(totalSeconds: number): string {
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}

export default function NewJobPage() {
  const t = useTranslations("upload");
  const te = useTranslations("errors");
  const locale = useLocale();
  const router = useRouter();
  const nf = new Intl.NumberFormat(locale);

  const [file, setFile] = useState<File | null>(null);
  const [language, setLanguage] = useState("fa");
  const [wantSummary, setWantSummary] = useState(true);
  const [dragActive, setDragActive] = useState(false);
  const [fileError, setFileError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [quota, setQuota] = useState<QuotaInfo | null>(null);

  const [isRecording, setIsRecording] = useState(false);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [micError, setMicError] = useState<string | null>(null);

  const fileInputRef = useRef<HTMLInputElement>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);

  useEffect(() => {
    if (!getToken()) router.replace("/login");
  }, [router]);

  useEffect(() => {
    let active = true;
    getQuota()
      .then((info) => {
        if (active) setQuota(info);
      })
      .catch(() => {});
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (!isRecording) return;
    const timer = setInterval(() => setElapsedSeconds((seconds) => seconds + 1), 1000);
    return () => clearInterval(timer);
  }, [isRecording]);

  useEffect(() => {
    return () => {
      const recorder = recorderRef.current;
      if (recorder && recorder.state !== "inactive") {
        recorder.stop();
        recorder.stream.getTracks().forEach((track) => track.stop());
      }
    };
  }, []);

  function acceptFile(candidate: File) {
    if (!candidate.type.startsWith("audio/") && !candidate.type.startsWith("video/")) {
      setFileError(t("unsupportedFile"));
      return;
    }
    setFileError(null);
    setUploadError(null);
    setFile(candidate);
  }

  function handleDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setDragActive(false);
    const dropped = event.dataTransfer.files?.[0];
    if (dropped) acceptFile(dropped);
  }

  async function startRecording() {
    setMicError(null);
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
      setMicError(t("micError"));
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      chunksRef.current = [];
      const recorder = new MediaRecorder(stream);
      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) chunksRef.current.push(event.data);
      };
      recorder.onstop = () => {
        const blob = new Blob(chunksRef.current, { type: "audio/webm" });
        const recorded = new File([blob], `recording-${Date.now()}.webm`, {
          type: "audio/webm",
        });
        setFile(recorded);
        setFileError(null);
        setUploadError(null);
        stream.getTracks().forEach((track) => track.stop());
      };
      recorder.start();
      recorderRef.current = recorder;
      setElapsedSeconds(0);
      setIsRecording(true);
    } catch {
      setMicError(t("micError"));
    }
  }

  function stopRecording() {
    const recorder = recorderRef.current;
    if (recorder && recorder.state !== "inactive") recorder.stop();
    recorderRef.current = null;
    setIsRecording(false);
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!file) {
      setFileError(t("noFile"));
      return;
    }
    setUploading(true);
    setUploadError(null);
    try {
      const result = await uploadJob(file, { language, wantSummary });
      router.push(`/jobs/${result.id}`);
    } catch (error) {
      setUploading(false);
      if (error instanceof ApiError) {
        if (error.status === 402) setUploadError(te("quota"));
        else if (error.status === 0) setUploadError(te("network"));
        else setUploadError(te("generic"));
      } else {
        setUploadError(te("network"));
      }
    }
  }

  const dropzoneClasses = `flex min-h-44 w-full cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed p-8 text-center transition-colors ${
    dragActive
      ? "border-teal-600 bg-teal-50"
      : "border-stone-300 bg-white hover:border-teal-600 hover:bg-teal-50/40"
  } ${uploading || isRecording ? "pointer-events-none opacity-60" : ""}`;

  const controlButtonClasses =
    "inline-flex min-h-11 items-center justify-center gap-2 rounded-xl px-5 text-sm font-bold transition-colors focus-visible:ring-2 focus-visible:ring-teal-700 focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-60";

  return (
    <div className="mx-auto w-full max-w-2xl px-4 py-10 sm:px-6 sm:py-14">
      <header className="mb-8">
        <h1 className="text-2xl font-bold text-stone-900 sm:text-3xl">{t("title")}</h1>
        <p className="mt-2 text-sm leading-7 text-stone-600">{t("subtitle")}</p>
      </header>

      <form onSubmit={handleSubmit} noValidate className="space-y-5">
        <div
          onDragOver={(event) => {
            event.preventDefault();
            setDragActive(true);
          }}
          onDragLeave={() => setDragActive(false)}
          onDrop={handleDrop}
        >
          <input
            ref={fileInputRef}
            id="job-file"
            type="file"
            accept="audio/*,video/*"
            className="sr-only"
            disabled={uploading || isRecording}
            onChange={(event) => {
              const picked = event.target.files?.[0];
              if (picked) acceptFile(picked);
              event.target.value = "";
            }}
          />
          <label htmlFor="job-file" className={dropzoneClasses}>
            <span className="flex h-12 w-12 items-center justify-center rounded-xl bg-teal-50 text-teal-700">
              <Upload className="h-6 w-6" aria-hidden="true" />
            </span>
            <span className="mt-1 text-sm font-bold text-stone-900">{t("dropzoneTitle")}</span>
            <span className="text-sm text-stone-600">{t("dropzoneSubtitle")}</span>
            <span className="mt-1 text-xs text-stone-500">{t("dropzoneHint")}</span>
          </label>
        </div>

        {fileError ? (
          <p role="alert" className="text-sm text-red-700">
            {fileError}
          </p>
        ) : null}

        {file ? (
          <div className="flex items-center justify-between gap-3 rounded-xl border border-stone-200 bg-white p-4 shadow-sm">
            <div className="flex min-w-0 items-center gap-3">
              <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-teal-50 text-teal-700">
                <FileText className="h-5 w-5" aria-hidden="true" />
              </span>
              <div className="min-w-0">
                <p className="text-xs text-stone-500">{t("selectedLabel")}</p>
                <p dir="auto" className="truncate text-sm font-bold text-stone-900">
                  {file.name}
                </p>
                <p className="text-xs text-stone-500">{formatFileSize(file.size)}</p>
              </div>
            </div>
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              disabled={uploading || isRecording}
              className="shrink-0 rounded-lg px-2 py-1 text-sm font-bold text-teal-700 underline-offset-4 transition-colors hover:text-teal-600 hover:underline focus-visible:ring-2 focus-visible:ring-teal-700 disabled:opacity-50"
            >
              {t("changeFile")}
            </button>
          </div>
        ) : null}

        <div className="rounded-xl border border-stone-200 bg-white p-4 shadow-sm sm:p-6">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <p className="text-sm leading-6 text-stone-600">
              {isRecording ? t("recordingHint") : t("recordHintIdle")}
            </p>
            <div className="flex items-center gap-3">
              {isRecording ? (
                <span
                  className="inline-flex items-center gap-2 font-mono text-sm font-bold text-red-700"
                  aria-live="polite"
                >
                  <span
                    className="h-2.5 w-2.5 animate-pulse rounded-full bg-red-600"
                    aria-hidden="true"
                  />
                  {formatClock(elapsedSeconds)}
                </span>
              ) : null}
              <button
                type="button"
                onClick={isRecording ? stopRecording : startRecording}
                disabled={uploading}
                className={
                  isRecording
                    ? `${controlButtonClasses} bg-red-600 text-white hover:bg-red-500`
                    : `${controlButtonClasses} border border-teal-700 text-teal-800 hover:bg-teal-50`
                }
              >
                {isRecording ? (
                  <>
                    <Square className="h-4 w-4" aria-hidden="true" />
                    {t("recordStop")}
                  </>
                ) : (
                  <>
                    <Mic className="h-4 w-4" aria-hidden="true" />
                    {t("recordButton")}
                  </>
                )}
              </button>
            </div>
          </div>
          {micError ? (
            <p role="alert" className="mt-3 text-sm text-red-700">
              {micError}
            </p>
          ) : null}
        </div>

        <div className="space-y-5 rounded-xl border border-stone-200 bg-white p-4 shadow-sm sm:p-6">
          <div>
            <label htmlFor="job-language" className="mb-1.5 block text-sm font-bold text-stone-800">
              {t("languageLabel")}
            </label>
            <div className="relative">
              <select
                id="job-language"
                value={language}
                onChange={(event) => setLanguage(event.target.value)}
                disabled={uploading}
                className="h-11 w-full appearance-none rounded-lg border border-stone-300 bg-white px-3 pe-10 text-base text-stone-900 focus:border-teal-600 focus:outline-none focus:ring-2 focus:ring-teal-600/20 disabled:cursor-not-allowed disabled:bg-stone-50 sm:text-sm"
              >
                <option value="fa">{t("languageFa")}</option>
                <option value="en">{t("languageEn")}</option>
                <option value="auto">{t("languageAuto")}</option>
              </select>
              <ChevronDown
                className="pointer-events-none absolute end-3 top-1/2 h-4 w-4 -translate-y-1/2 text-stone-400"
                aria-hidden="true"
              />
            </div>
          </div>

          <label className="flex items-start gap-3">
            <input
              type="checkbox"
              checked={wantSummary}
              onChange={(event) => setWantSummary(event.target.checked)}
              disabled={uploading}
              className="mt-1 h-4 w-4 shrink-0 accent-teal-700"
            />
            <span>
              <span className="block text-sm font-bold text-stone-800">{t("summaryLabel")}</span>
              <span className="mt-0.5 block text-xs text-stone-500">{t("summaryHint")}</span>
            </span>
          </label>

          {quota ? (
            <p className="border-t border-stone-100 pt-4 text-xs leading-6 text-stone-500">
              {quota.remaining_minutes > 0
                ? t("quotaLine", {
                    remaining: nf.format(quota.remaining_minutes),
                    limit: nf.format(quota.limit_minutes),
                  })
                : t("quotaEmpty")}
            </p>
          ) : null}
        </div>

        {uploadError ? (
          <div
            role="alert"
            className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm leading-7 text-red-800"
          >
            {uploadError}
          </div>
        ) : null}

        <button
          type="submit"
          disabled={uploading || isRecording}
          className="inline-flex min-h-11 w-full items-center justify-center gap-2 rounded-xl bg-teal-700 px-5 text-sm font-bold text-white shadow-sm transition-colors hover:bg-teal-600 focus-visible:ring-2 focus-visible:ring-teal-700 focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {uploading ? (
            <>
              <span
                className="h-4 w-4 animate-spin rounded-full border-2 border-white/40 border-t-white"
                aria-hidden="true"
              />
              {t("submitting")}
            </>
          ) : (
            t("submit")
          )}
        </button>
      </form>
    </div>
  );
}
