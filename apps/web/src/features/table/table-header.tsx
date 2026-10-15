"use client";

import { Check, Download, Pencil, X } from "lucide-react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { Skeleton } from "@/components/ui/misc";
import { QualityScore } from "@/features/quality/quality-view";
import { exportUrl, useQuality, useRenameDataset } from "@/lib/api/hooks";

export function TableHeader({
  ws,
  datasetId,
  name,
  maskPersonal,
}: {
  ws: number;
  datasetId: number;
  name: string | undefined;
  maskPersonal: boolean;
}) {
  const t = useTranslations("table");
  const tq = useTranslations("quality");
  const tc = useTranslations("common");
  const quality = useQuality(datasetId);
  const rename = useRenameDataset();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");

  return (
    <header className="mb-6 flex flex-wrap items-start justify-between gap-4">
      <div className="min-w-0">
        {editing ? (
          <form
            className="flex items-center gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              if (draft.trim()) {
                rename.mutate({ id: datasetId, name: draft.trim() }, { onSuccess: () => setEditing(false) });
              }
            }}
          >
            <input
              autoFocus
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              maxLength={120}
              aria-label={t("rename")}
              className="display h-12 w-[min(70vw,28rem)] rounded-lg border border-accent bg-paper-raised px-3 text-2xl font-semibold focus:outline-none"
            />
            <button type="submit" className="rounded-md p-2 text-ok hover:bg-paper-sunken" aria-label={t("save")}>
              <Check className="size-5" />
            </button>
            <button type="button" onClick={() => setEditing(false)} className="rounded-md p-2 text-ink-muted hover:bg-paper-sunken" aria-label={tc("cancel")}>
              <X className="size-5" />
            </button>
          </form>
        ) : (
          <h1 className="group display flex items-center gap-2 text-3xl font-semibold sm:text-4xl">
            {name ?? <Skeleton className="h-10 w-72" />}
            {name ? (
              <button
                type="button"
                onClick={() => {
                  setDraft(name);
                  setEditing(true);
                }}
                className="rounded-md p-1.5 text-ink-faint opacity-60 hover:bg-paper-sunken hover:text-ink group-hover:opacity-100"
                aria-label={t("rename")}
                title={t("rename")}
              >
                <Pencil className="size-4" />
              </button>
            ) : null}
          </h1>
        )}
        <p className="mt-2 text-sm text-ink-muted">{t("cellHint")}</p>
      </div>

      <div className="flex items-center gap-3">
        {quality.data?.score != null && quality.data.grade ? (
          <Link
            href={`/w/${ws}/veri/${datasetId}/kalite`}
            className="flex items-center gap-2 rounded-xl border border-rule bg-paper-raised py-1.5 pr-3 pl-1.5 text-sm hover:border-accent/50"
          >
            <QualityScore score={quality.data.score} grade={quality.data.grade} size={36} />
            <span>
              <span className="block text-xs text-ink-faint">{tq("score")}</span>
              <span className="font-medium">{tq(`grades.${quality.data.grade}`)}</span>
            </span>
          </Link>
        ) : null}
        <details className="relative">
          <summary className="inline-flex h-10 cursor-pointer list-none items-center gap-2 rounded-lg border border-rule-strong bg-paper-raised px-4 text-sm font-medium hover:bg-paper-sunken [&::-webkit-details-marker]:hidden">
            <Download className="size-4" />
            {t("export")}
          </summary>
          <div className="absolute right-0 z-20 mt-2 w-60 rounded-xl border border-rule bg-paper-raised p-1.5 shadow-card">
            {(["xlsx", "csv"] as const).map((format) => (
              <a
                key={format}
                href={exportUrl(datasetId, format, maskPersonal)}
                className="block rounded-lg px-3 py-2 text-sm hover:bg-paper-sunken"
                download
              >
                {format === "xlsx" ? t("exportXlsx") : t("exportCsv")}
              </a>
            ))}
            {maskPersonal ? <p className="px-3 pt-1 pb-1.5 text-xs text-ink-faint">{t("exportMasked")}</p> : null}
          </div>
        </details>
      </div>
    </header>
  );
}
