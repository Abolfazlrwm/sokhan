"use client";

import { useState, type FormEvent } from "react";
import { useTranslations } from "next-intl";
import { useRouter } from "@/i18n/navigation";
import { ApiError, login, register, setToken, tokenLogin } from "@/lib/api";

type Mode = "login" | "register" | "code";

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export default function LoginPage() {
  const t = useTranslations("login");
  const te = useTranslations("errors");
  const router = useRouter();

  const [mode, setMode] = useState<Mode>("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [emailError, setEmailError] = useState<string | null>(null);
  const [passwordError, setPasswordError] = useState<string | null>(null);
  const [codeError, setCodeError] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  function switchMode(next: Mode) {
    if (next === mode) return;
    setMode(next);
    setEmailError(null);
    setPasswordError(null);
    setCodeError(null);
    setFormError(null);
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFormError(null);

    let nextEmailError: string | null = null;
    let nextPasswordError: string | null = null;
    let nextCodeError: string | null = null;

    if (mode === "code") {
      if (!code.trim()) nextCodeError = te("codeRequired");
    } else {
      const trimmedEmail = email.trim();
      if (!trimmedEmail) {
        nextEmailError = te("emailRequired");
      } else if (!EMAIL_PATTERN.test(trimmedEmail)) {
        nextEmailError = te("emailInvalid");
      }

      if (!password) {
        nextPasswordError = te("passwordRequired");
      } else if (mode === "register" && password.length < 8) {
        nextPasswordError = te("passwordTooShort");
      }
    }

    setEmailError(nextEmailError);
    setPasswordError(nextPasswordError);
    setCodeError(nextCodeError);
    if (nextEmailError || nextPasswordError || nextCodeError) return;

    setPending(true);
    try {
      const result =
        mode === "login"
          ? await login(email.trim(), password)
          : mode === "register"
            ? await register(email.trim(), password)
            : await tokenLogin(code.trim());
      setToken(result.api_token);
      router.push("/new");
    } catch (error) {
      setPending(false);
      if (error instanceof ApiError) {
        if (error.status === 401) {
          setFormError(mode === "code" ? te("invalidCode") : te("invalidCredentials"));
        } else if (error.status === 409) {
          setFormError(te("emailTaken"));
        } else if (error.status === 422) {
          setFormError(te("validation"));
        } else if (error.status === 0) {
          setFormError(te("network"));
        } else {
          setFormError(te("generic"));
        }
      } else {
        setFormError(te("network"));
      }
    }
  }

  const inputClasses =
    "h-11 w-full rounded-lg border border-stone-300 bg-white px-3 text-base text-stone-900 placeholder:text-stone-400 focus:border-teal-600 focus:outline-none focus:ring-2 focus:ring-teal-600/20 sm:text-sm";

  const tabs: Array<{ id: Mode; label: string }> = [
    { id: "login", label: t("tabLogin") },
    { id: "register", label: t("tabRegister") },
    { id: "code", label: t("tabCode") },
  ];

  return (
    <div className="mx-auto w-full max-w-md px-4 py-12 sm:px-6 sm:py-16">
      <div className="rounded-xl border border-stone-200 bg-white p-6 shadow-sm sm:p-8">
        <h1 className="text-xl font-bold text-stone-900 sm:text-2xl">{t("title")}</h1>
        <p className="mt-2 text-sm leading-7 text-stone-600">{t("subtitle")}</p>

        <div
          role="tablist"
          aria-label={t("tabsLabel")}
          className="mt-6 grid grid-cols-3 gap-1 rounded-xl bg-stone-100 p-1"
        >
          {tabs.map((tab) => (
            <button
              key={tab.id}
              type="button"
              role="tab"
              id={`tab-${tab.id}`}
              aria-selected={mode === tab.id}
              aria-controls={`panel-${tab.id}`}
              onClick={() => switchMode(tab.id)}
              className={`min-h-10 rounded-lg px-2 text-sm font-bold transition-colors focus-visible:ring-2 focus-visible:ring-teal-700 ${
                mode === tab.id
                  ? "bg-white text-teal-800 shadow-sm"
                  : "text-stone-600 hover:text-stone-900"
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        <form
          role="tabpanel"
          id={`panel-${mode}`}
          aria-labelledby={`tab-${mode}`}
          onSubmit={handleSubmit}
          noValidate
          className="mt-6 space-y-4"
        >
          {mode !== "code" ? (
            <>
              <div>
                <label
                  htmlFor="login-email"
                  className="mb-1.5 block text-sm font-bold text-stone-800"
                >
                  {t("emailLabel")}
                </label>
                <input
                  id="login-email"
                  name="email"
                  type="email"
                  dir="ltr"
                  autoComplete="email"
                  value={email}
                  onChange={(event) => {
                    setEmail(event.target.value);
                    if (emailError) setEmailError(null);
                  }}
                  placeholder={t("emailPlaceholder")}
                  aria-invalid={emailError ? true : undefined}
                  className={inputClasses}
                />
                {emailError ? (
                  <p className="mt-1.5 text-sm text-red-700">{emailError}</p>
                ) : null}
              </div>
              <div>
                <label
                  htmlFor="login-password"
                  className="mb-1.5 block text-sm font-bold text-stone-800"
                >
                  {t("passwordLabel")}
                </label>
                <input
                  id="login-password"
                  name="password"
                  type="password"
                  dir="ltr"
                  autoComplete={mode === "register" ? "new-password" : "current-password"}
                  value={password}
                  onChange={(event) => {
                    setPassword(event.target.value);
                    if (passwordError) setPasswordError(null);
                  }}
                  placeholder={t("passwordPlaceholder")}
                  aria-invalid={passwordError ? true : undefined}
                  className={inputClasses}
                />
                {passwordError ? (
                  <p className="mt-1.5 text-sm text-red-700">{passwordError}</p>
                ) : mode === "register" ? (
                  <p className="mt-1.5 text-xs text-stone-500">{t("passwordHintRegister")}</p>
                ) : null}
              </div>
            </>
          ) : (
            <div>
              <label
                htmlFor="login-code"
                className="mb-1.5 block text-sm font-bold text-stone-800"
              >
                {t("codeLabel")}
              </label>
              <input
                id="login-code"
                name="code"
                type="text"
                dir="ltr"
                autoComplete="off"
                value={code}
                onChange={(event) => {
                  setCode(event.target.value);
                  if (codeError) setCodeError(null);
                }}
                placeholder={t("codePlaceholder")}
                aria-invalid={codeError ? true : undefined}
                className={inputClasses}
              />
              {codeError ? <p className="mt-1.5 text-sm text-red-700">{codeError}</p> : null}
              <p className="mt-1.5 text-xs text-stone-500">{t("codeHint")}</p>
            </div>
          )}

          {formError ? (
            <div
              role="alert"
              className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm leading-6 text-red-800"
            >
              {formError}
            </div>
          ) : null}

          <button
            type="submit"
            disabled={pending}
            className="inline-flex min-h-11 w-full items-center justify-center gap-2 rounded-xl bg-teal-700 px-5 text-sm font-bold text-white shadow-sm transition-colors hover:bg-teal-600 focus-visible:ring-2 focus-visible:ring-teal-700 focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {pending ? (
              <>
                <span
                  className="h-4 w-4 animate-spin rounded-full border-2 border-white/40 border-t-white"
                  aria-hidden="true"
                />
                {t("pending")}
              </>
            ) : mode === "register" ? (
              t("registerSubmit")
            ) : (
              t("loginSubmit")
            )}
          </button>
        </form>
      </div>
    </div>
  );
}
