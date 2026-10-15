import {
  Database,
  FileSpreadsheet,
  GitMerge,
  History,
  Languages,
  MousePointerClick,
  ShieldCheck,
  Sparkles,
  Undo2,
  Users,
  type LucideIcon,
} from "lucide-react";
import { getTranslations } from "next-intl/server";

import { Logo, ThemeToggle } from "@/components/brand";
import { BeforeAfter } from "@/components/landing/before-after";
import { DemoButton, UploadOwnButton } from "@/components/landing/start-buttons";

const REPO_URL = "https://github.com/";

// Mean over five generated ledgers, see README → Benchmark. Kept in sync by hand.
const BENCHMARK = { dates: "%100", auto: "0,90", reviewed: "0,93", cards: 11 };

export default async function LandingPage() {
  const t = await getTranslations("landing");

  const problems = ["formats", "names", "trust"] as const;
  const steps: { key: "upload" | "recognize" | "match" | "keep"; icon: LucideIcon }[] = [
    { key: "upload", icon: FileSpreadsheet },
    { key: "recognize", icon: Sparkles },
    { key: "match", icon: GitMerge },
    { key: "keep", icon: History },
  ];
  const reasons: { key: "persistent" | "entities" | "turkish" | "provenance" | "undo" | "privacy"; icon: LucideIcon }[] = [
    { key: "persistent", icon: Database },
    { key: "entities", icon: Users },
    { key: "turkish", icon: Languages },
    { key: "provenance", icon: MousePointerClick },
    { key: "undo", icon: Undo2 },
    { key: "privacy", icon: ShieldCheck },
  ];

  return (
    <div className="min-h-dvh">
      <header className="mx-auto flex max-w-6xl items-center justify-between px-4 py-5 md:px-8">
        <Logo />
        <nav className="flex items-center gap-1 text-sm text-ink-muted">
          <a href="#nasil" className="hidden rounded-lg px-3 py-2 hover:text-ink sm:block">
            {t("nav.how")}
          </a>
          <a href="#neden" className="hidden rounded-lg px-3 py-2 hover:text-ink sm:block">
            {t("nav.why")}
          </a>
          <a href={REPO_URL} className="hidden rounded-lg px-3 py-2 hover:text-ink sm:block">
            {t("nav.source")}
          </a>
          <ThemeToggle />
        </nav>
      </header>

      <main>
        {/* Hero */}
        <section className="mx-auto grid max-w-6xl items-center gap-12 px-4 pt-8 pb-20 md:px-8 lg:grid-cols-[1.05fr_1fr] lg:pt-16">
          <div className="animate-fade-up">
            <p className="text-sm font-medium text-accent">{t("hero.eyebrow")}</p>
            <h1 className="display mt-4 text-[2.6rem] leading-[1.05] font-semibold sm:text-6xl">
              {t("hero.title")}
            </h1>
            <p className="mt-6 max-w-xl text-lg leading-relaxed text-ink-muted">{t("hero.lead")}</p>
            <div className="mt-8 flex flex-wrap items-start gap-3">
              <DemoButton />
              <UploadOwnButton />
            </div>
            <p className="mt-5 text-sm text-ink-faint">{t("hero.assurance")}</p>
          </div>
          <div className="animate-fade-up [animation-delay:150ms]">
            <BeforeAfter />
          </div>
        </section>

        {/* Problem */}
        <section className="border-y border-rule bg-paper-raised/60">
          <div className="mx-auto max-w-6xl px-4 py-20 md:px-8">
            <h2 className="display max-w-2xl text-3xl font-semibold sm:text-4xl">{t("problem.title")}</h2>
            <div className="mt-10 grid gap-6 md:grid-cols-3">
              {problems.map((key) => (
                <div key={key} className="border-l-2 border-(--margin-line) pl-5">
                  <h3 className="font-semibold">{t(`problem.items.${key}.title`)}</h3>
                  <p className="mt-2 text-sm leading-relaxed text-ink-muted">{t(`problem.items.${key}.body`)}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* How */}
        <section id="nasil" className="mx-auto max-w-6xl scroll-mt-8 px-4 py-20 md:px-8">
          <h2 className="display text-3xl font-semibold sm:text-4xl">{t("how.title")}</h2>
          <ol className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {steps.map(({ key, icon: Icon }, i) => (
              <li key={key} className="relative rounded-2xl border border-rule bg-paper-raised p-5">
                <div className="flex items-center justify-between">
                  <span className="grid size-10 place-items-center rounded-xl bg-accent-soft text-accent">
                    <Icon className="size-5" />
                  </span>
                  <span className="display text-3xl font-semibold text-rule-strong tnum">{i + 1}</span>
                </div>
                <h3 className="mt-4 font-semibold">{t(`how.steps.${key}.title`)}</h3>
                <p className="mt-2 text-sm leading-relaxed text-ink-muted">{t(`how.steps.${key}.body`)}</p>
              </li>
            ))}
          </ol>
        </section>

        {/* Why */}
        <section id="neden" className="scroll-mt-8 border-y border-rule bg-paper-raised/60">
          <div className="mx-auto max-w-6xl px-4 py-20 md:px-8">
            <h2 className="display text-3xl font-semibold sm:text-4xl">{t("why.title")}</h2>
            <p className="mt-4 max-w-2xl text-ink-muted">{t("why.lead")}</p>
            <div className="mt-10 grid gap-x-10 gap-y-8 sm:grid-cols-2 lg:grid-cols-3">
              {reasons.map(({ key, icon: Icon }) => (
                <div key={key} className="flex gap-4">
                  <Icon className="mt-0.5 size-5 shrink-0 text-accent" />
                  <div>
                    <h3 className="font-semibold">{t(`why.items.${key}.title`)}</h3>
                    <p className="mt-1.5 text-sm leading-relaxed text-ink-muted">{t(`why.items.${key}.body`)}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* Numbers */}
        <section className="mx-auto max-w-6xl px-4 py-20 md:px-8">
          <h2 className="display text-3xl font-semibold sm:text-4xl">{t("numbers.title")}</h2>
          <p className="mt-4 max-w-2xl text-ink-muted">{t("numbers.lead")}</p>
          <dl className="mt-10 grid gap-6 sm:grid-cols-3">
            {[
              { value: BENCHMARK.dates, label: t("numbers.dates") },
              { value: BENCHMARK.auto, label: t("numbers.auto") },
              { value: BENCHMARK.reviewed, label: t("numbers.reviewed", { cards: BENCHMARK.cards }) },
            ].map((item) => (
              <div key={item.label} className="rounded-2xl border border-rule bg-paper-raised p-6">
                <dd className="display text-5xl font-semibold text-accent tnum">{item.value}</dd>
                <dt className="mt-2 text-sm text-ink-muted">{item.label}</dt>
              </div>
            ))}
          </dl>
          <p className="mt-4 text-xs text-ink-faint">{t("numbers.note")}</p>
        </section>

        {/* CTA */}
        <section className="mx-auto max-w-6xl px-4 pb-24 md:px-8">
          <div className="ruled flex flex-col items-start gap-6 rounded-3xl border border-rule px-6 py-12 pl-16 sm:pl-20 md:flex-row md:items-center md:justify-between">
            <div>
              <h2 className="display text-2xl font-semibold sm:text-3xl">{t("cta.title")}</h2>
              <p className="mt-2 max-w-lg text-ink-muted">{t("cta.body")}</p>
            </div>
            <DemoButton />
          </div>
        </section>
      </main>

      <footer className="border-t border-rule">
        <div className="mx-auto flex max-w-6xl flex-col items-start justify-between gap-2 px-4 py-8 text-sm text-ink-faint sm:flex-row sm:items-center md:px-8">
          <Logo />
          <p>
            {t("footer.license")} · {t("footer.built")}
          </p>
        </div>
      </footer>
    </div>
  );
}
