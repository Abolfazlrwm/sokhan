import { getTranslations, setRequestLocale } from "next-intl/server";
import { ArrowRight, GraduationCap, TextSearch, Voicemail, type LucideIcon } from "lucide-react";
import { Link } from "@/i18n/navigation";

const waveBars = [12, 20, 30, 22, 34, 40, 28, 16, 26, 36, 20, 30, 14, 24, 32, 18, 26, 12, 22, 16];

interface Feature {
  icon: LucideIcon;
  title: string;
  desc: string;
  soon: boolean;
}

export default async function LandingPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);

  const t = await getTranslations("landing");
  const nf = new Intl.NumberFormat(locale);

  const features: Feature[] = [
    {
      icon: GraduationCap,
      title: t("featureLectureTitle"),
      desc: t("featureLectureDesc"),
      soon: false,
    },
    {
      icon: TextSearch,
      title: t("featureInterviewTitle"),
      desc: t("featureInterviewDesc"),
      soon: true,
    },
    {
      icon: Voicemail,
      title: t("featureVoiceTitle"),
      desc: t("featureVoiceDesc"),
      soon: false,
    },
  ];

  const steps = [
    { title: t("step1Title"), desc: t("step1Desc") },
    { title: t("step2Title"), desc: t("step2Desc") },
    { title: t("step3Title"), desc: t("step3Desc") },
  ];

  return (
    <div className="mx-auto w-full max-w-5xl px-4 sm:px-6">
      <section className="py-16 text-center sm:py-24" aria-labelledby="hero-title">
        <h1
          id="hero-title"
          className="mx-auto max-w-3xl text-4xl font-bold leading-[1.3] tracking-tight text-stone-900 sm:text-5xl sm:leading-[1.25]"
        >
          {t("headline")}
        </h1>
        <p className="mx-auto mt-5 max-w-2xl text-base leading-8 text-stone-600 sm:text-lg">
          {t("subheadline")}
        </p>
        <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
          <Link
            href="/new"
            className="inline-flex min-h-11 items-center gap-2 rounded-xl bg-teal-700 px-6 text-sm font-bold text-white shadow-sm transition-colors hover:bg-teal-600 focus-visible:ring-2 focus-visible:ring-teal-700 focus-visible:ring-offset-2"
          >
            {t("startCta")}
            <ArrowRight className="h-4 w-4 rtl:-scale-x-100" aria-hidden="true" />
          </Link>
          <Link
            href="/login"
            className="inline-flex min-h-11 items-center rounded-xl border border-stone-300 bg-white px-6 text-sm font-bold text-stone-800 transition-colors hover:border-teal-700 hover:text-teal-800 focus-visible:ring-2 focus-visible:ring-teal-700 focus-visible:ring-offset-2"
          >
            {t("loginCta")}
          </Link>
        </div>
        <svg
          viewBox="0 0 200 48"
          className="mx-auto mt-14 h-12 w-full max-w-md text-teal-700/60"
          aria-hidden="true"
          fill="currentColor"
        >
          {waveBars.map((height, index) => (
            <rect
              key={index}
              x={index * 10 + 2}
              y={(48 - height) / 2}
              width="6"
              height={height}
              rx="3"
            />
          ))}
        </svg>
      </section>

      <section className="pb-16 sm:pb-24" aria-labelledby="features-title">
        <div className="mx-auto max-w-2xl text-center">
          <h2 id="features-title" className="text-2xl font-bold text-stone-900 sm:text-3xl">
            {t("featuresTitle")}
          </h2>
          <p className="mt-3 text-sm leading-7 text-stone-600 sm:text-base">
            {t("featuresSubtitle")}
          </p>
        </div>
        <ul className="mt-10 grid gap-5 sm:gap-6 md:grid-cols-3">
          {features.map((feature) => (
            <li
              key={feature.title}
              className="rounded-xl border border-stone-200 bg-white p-6 shadow-sm transition-shadow hover:shadow-md"
            >
              <div className="flex h-11 w-11 items-center justify-center rounded-lg bg-teal-50 text-teal-700">
                <feature.icon className="h-6 w-6" aria-hidden="true" />
              </div>
              <div className="mt-4 flex flex-wrap items-center gap-2">
                <h3 className="text-lg font-bold text-stone-900">{feature.title}</h3>
                {feature.soon ? (
                  <span className="rounded-full bg-amber-100 px-2.5 py-0.5 text-xs font-bold text-amber-800">
                    {t("featureSoonBadge")}
                  </span>
                ) : null}
              </div>
              <p className="mt-2 text-sm leading-7 text-stone-600">{feature.desc}</p>
            </li>
          ))}
        </ul>
      </section>

      <section className="pb-16 sm:pb-24" aria-labelledby="how-title">
        <div className="mx-auto max-w-2xl text-center">
          <h2 id="how-title" className="text-2xl font-bold text-stone-900 sm:text-3xl">
            {t("howTitle")}
          </h2>
          <p className="mt-3 text-sm leading-7 text-stone-600 sm:text-base">{t("howSubtitle")}</p>
        </div>
        <ol className="mt-10 grid gap-5 sm:gap-6 md:grid-cols-3">
          {steps.map((step, index) => (
            <li key={step.title} className="rounded-xl border border-stone-200 bg-white p-6 shadow-sm">
              <span className="flex h-9 w-9 items-center justify-center rounded-full bg-teal-700 text-sm font-bold text-white">
                {nf.format(index + 1)}
              </span>
              <h3 className="mt-4 font-bold text-stone-900">{step.title}</h3>
              <p className="mt-2 text-sm leading-7 text-stone-600">{step.desc}</p>
            </li>
          ))}
        </ol>
      </section>

      <section className="pb-20 sm:pb-28" aria-labelledby="cta-title">
        <div className="rounded-xl border border-teal-200 bg-teal-50 p-8 text-center sm:p-12">
          <h2 id="cta-title" className="text-2xl font-bold text-teal-900 sm:text-3xl">
            {t("ctaTitle")}
          </h2>
          <p className="mx-auto mt-3 max-w-xl text-sm leading-7 text-teal-800/90 sm:text-base">
            {t("ctaDesc")}
          </p>
          <Link
            href="/new"
            className="mt-6 inline-flex min-h-11 items-center gap-2 rounded-xl bg-teal-700 px-6 text-sm font-bold text-white shadow-sm transition-colors hover:bg-teal-600 focus-visible:ring-2 focus-visible:ring-teal-700 focus-visible:ring-offset-2"
          >
            {t("startCta")}
            <ArrowRight className="h-4 w-4 rtl:-scale-x-100" aria-hidden="true" />
          </Link>
        </div>
      </section>
    </div>
  );
}
