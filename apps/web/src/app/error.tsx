"use client";

import { useTranslations } from "next-intl";

import { Button } from "@/components/ui/button";

export default function ErrorPage({ reset }: { error: Error; reset: () => void }) {
  const t = useTranslations("errors");
  const tc = useTranslations("common");
  return (
    <main className="mx-auto flex min-h-[60dvh] max-w-md flex-col items-center justify-center px-6 text-center">
      <h1 className="display text-2xl font-semibold">{t("pageTitle")}</h1>
      <p className="mt-2 text-ink-muted">{tc("errorDetail")}</p>
      <Button className="mt-6" onClick={reset}>
        {tc("retry")}
      </Button>
    </main>
  );
}
