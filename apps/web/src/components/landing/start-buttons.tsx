"use client";

import { ArrowRight, FolderUp, Loader2 } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { createDemoWorkspace } from "@/lib/api/hooks";

/** The user's own workspace is created on first API start; it is always id 1 locally. */
export const OWN_WORKSPACE = 1;

export function DemoButton({ size = "lg" }: { size?: "md" | "lg" }) {
  const t = useTranslations("landing.hero");
  const tc = useTranslations("upload.errors");
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(false);

  async function start() {
    setBusy(true);
    setError(false);
    try {
      const workspace = await createDemoWorkspace();
      router.push(`/w/${workspace.id}/yukle?ornek=1`);
    } catch {
      setError(true);
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col items-start gap-2">
      <Button size={size} onClick={start} disabled={busy}>
        {busy ? <Loader2 className="animate-spin" /> : <ArrowRight />}
        {busy ? t("starting") : t("tryDemo")}
      </Button>
      {error ? (
        <p role="alert" className="text-sm text-bad">
          {tc("network")}
        </p>
      ) : null}
    </div>
  );
}

export function UploadOwnButton() {
  const t = useTranslations("landing.hero");
  return (
    <Button asChild variant="secondary" size="lg">
      <Link href={`/w/${OWN_WORKSPACE}/yukle`}>
        <FolderUp />
        {t("uploadOwn")}
      </Link>
    </Button>
  );
}
