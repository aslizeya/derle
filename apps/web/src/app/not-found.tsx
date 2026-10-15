import Link from "next/link";
import { getTranslations } from "next-intl/server";

import { Logo } from "@/components/brand";

export default async function NotFound() {
  const t = await getTranslations("errors");
  return (
    <main className="mx-auto flex min-h-dvh max-w-md flex-col items-center justify-center px-6 text-center">
      <Logo />
      <p className="display mt-10 text-7xl font-semibold text-rule-strong tnum">404</p>
      <h1 className="display mt-4 text-2xl font-semibold">{t("notFoundTitle")}</h1>
      <p className="mt-2 text-ink-muted">{t("notFoundBody")}</p>
      <Link href="/" className="mt-6 font-medium text-accent hover:underline">
        {t("home")}
      </Link>
    </main>
  );
}
