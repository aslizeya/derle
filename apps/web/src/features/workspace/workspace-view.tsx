"use client";

import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  Database,
  FileSpreadsheet,
  GitMerge,
  Loader2,
  Undo2,
  Upload,
} from "lucide-react";
import Link from "next/link";
import { useTranslations } from "next-intl";

import { DemoButton } from "@/components/landing/start-buttons";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState, ErrorState, Skeleton } from "@/components/ui/misc";
import { QualityScore } from "@/features/quality/quality-view";
import { useDatasets, useQuality, useUploads, useWorkspace } from "@/lib/api/hooks";
import { formatDateTime } from "@/lib/utils";

export function WorkspaceView({ ws }: { ws: number }) {
  const t = useTranslations("workspace");
  const tc = useTranslations("common");
  const tn = useTranslations("nav");
  const workspace = useWorkspace(ws);
  const datasets = useDatasets(ws);
  const uploads = useUploads(ws);

  if (workspace.isError || datasets.isError) {
    return (
      <ErrorState
        title={tc("error")}
        body={tc("errorDetail")}
        onRetry={() => {
          void workspace.refetch();
          void datasets.refetch();
        }}
        retryLabel={tc("retry")}
      />
    );
  }

  const summary = workspace.data;
  const loading = workspace.isPending || datasets.isPending;

  return (
    <div className="mx-auto max-w-5xl">
      <header className="mb-8 flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-sm text-ink-faint">{t("title")}</p>
          <h1 className="display mt-1 text-3xl font-semibold sm:text-4xl">
            {summary?.name ?? <Skeleton className="h-10 w-64" />}
          </h1>
        </div>
        <Button asChild>
          <Link href={`/w/${ws}/yukle`}>
            <Upload />
            {tn("upload")}
          </Link>
        </Button>
      </header>

      <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {(
          [
            ["records", summary?.records],
            ["entities", summary?.entities],
            ["uploads", summary?.uploads],
            ["pending", summary?.pending_matches],
          ] as const
        ).map(([key, value]) => (
          <div key={key} className="rounded-2xl border border-rule bg-paper-raised px-4 py-3">
            <dt className="text-xs text-ink-muted">{t(`stats.${key}`)}</dt>
            <dd className="display mt-1 text-3xl font-semibold tnum">
              {value === undefined ? <Skeleton className="h-9 w-16" /> : value.toLocaleString("tr-TR")}
            </dd>
          </div>
        ))}
      </dl>

      {summary && summary.pending_matches > 0 ? (
        <div className="mt-6 flex flex-col gap-4 rounded-2xl border border-warn/30 bg-warn-soft px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex gap-3">
            <GitMerge className="mt-0.5 size-5 shrink-0 text-warn" />
            <div>
              <p className="font-medium">{t("pendingCallout.title", { count: summary.pending_matches })}</p>
              <p className="mt-0.5 text-sm text-ink-muted">{t("pendingCallout.body")}</p>
            </div>
          </div>
          <Button asChild variant="secondary" className="shrink-0">
            <Link href={`/w/${ws}/eslestirme`}>
              {t("pendingCallout.action")}
              <ArrowRight />
            </Link>
          </Button>
        </div>
      ) : null}

      {!loading && datasets.data?.length === 0 ? (
        <EmptyState
          className="mt-10"
          icon={<FileSpreadsheet />}
          title={t("empty.title")}
          body={t("empty.body")}
        >
          <Button asChild>
            <Link href={`/w/${ws}/yukle`}>
              <Upload />
              {t("empty.upload")}
            </Link>
          </Button>
          {summary?.is_demo ? null : <DemoButton size="md" />}
        </EmptyState>
      ) : (
        <>
          <section className="mt-10">
            <h2 className="display mb-4 text-xl font-semibold">{t("datasets")}</h2>
            <div className="grid gap-3 sm:grid-cols-2">
              {loading
                ? [0, 1].map((i) => <Skeleton key={i} className="h-28 rounded-2xl" />)
                : datasets.data?.map((d) => (
                    <Link
                      key={d.id}
                      href={`/w/${ws}/veri/${d.id}`}
                      className="group rounded-2xl border border-rule bg-paper-raised p-5 transition-colors hover:border-accent/50"
                    >
                      <div className="flex items-start justify-between gap-3">
                        <Database className="size-5 text-accent" />
                        <DatasetQuality datasetId={d.id} />
                      </div>
                      <h3 className="mt-3 font-semibold">{d.name}</h3>
                      <p className="mt-1 text-sm text-ink-muted tnum">
                        {t("datasetMeta", { records: d.records, sources: d.sources })}
                      </p>
                      {d.duplicates > 0 ? (
                        <p className="mt-2 text-xs text-ink-faint tnum">
                          {t("duplicatesRemoved", { count: d.duplicates })}
                        </p>
                      ) : null}
                    </Link>
                  ))}
            </div>
          </section>

          <section className="mt-10">
            <h2 className="display mb-4 text-xl font-semibold">{t("uploads")}</h2>
            <ul className="divide-y divide-rule overflow-hidden rounded-2xl border border-rule bg-paper-raised">
              {uploads.isPending
                ? [0, 1, 2].map((i) => (
                    <li key={i} className="px-5 py-4">
                      <Skeleton className="h-5 w-1/2" />
                    </li>
                  ))
                : uploads.data?.map((u) => (
                    <li key={u.id} className="flex flex-wrap items-center gap-x-4 gap-y-1 px-5 py-3.5">
                      <UploadStatusIcon status={u.status} />
                      <div className="min-w-0 flex-1">
                        <p className="truncate font-medium">{u.filename}</p>
                        <p className="text-xs text-ink-faint tnum">
                          {formatDateTime(u.created_at)} · {tc("records", { count: u.records })}
                        </p>
                      </div>
                      <Badge tone={u.status === "done" ? "ok" : u.status === "failed" ? "bad" : "neutral"}>
                        {t(`uploadStatus.${u.status as "done"}`)}
                      </Badge>
                      {u.status !== "failed" ? (
                        <Link
                          href={`/w/${ws}/yuklemeler/${u.id}`}
                          className="text-sm font-medium text-accent hover:underline"
                        >
                          {t("review")}
                        </Link>
                      ) : null}
                    </li>
                  ))}
            </ul>
          </section>
        </>
      )}
    </div>
  );
}

function DatasetQuality({ datasetId }: { datasetId: number }) {
  const t = useTranslations("quality");
  const quality = useQuality(datasetId);
  if (quality.data?.score == null || !quality.data.grade) return <ArrowRight className="size-4 text-ink-faint" />;
  return (
    <span className="flex items-center gap-2 text-xs text-ink-muted" title={t("score")}>
      {t(`grades.${quality.data.grade}`)}
      <QualityScore score={quality.data.score} grade={quality.data.grade} size={34} />
    </span>
  );
}

function UploadStatusIcon({ status }: { status: string }) {
  if (status === "done") return <CheckCircle2 className="size-4 text-ok" />;
  if (status === "failed") return <AlertTriangle className="size-4 text-bad" />;
  if (status === "undone") return <Undo2 className="size-4 text-ink-faint" />;
  return <Loader2 className="size-4 animate-spin text-ink-faint" />;
}
