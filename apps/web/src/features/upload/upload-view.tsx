"use client";

import { ArrowRight, GitMerge, Sparkles, Table2 } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { ErrorState } from "@/components/ui/misc";
import { fetchDemoFiles, useWorkspace } from "@/lib/api/hooks";

import { Dropzone } from "./dropzone";
import { JobCard } from "./job-card";
import { useUploadQueue } from "./use-upload-queue";

export function UploadView({ workspaceId, demo }: { workspaceId: number; demo: boolean }) {
  const t = useTranslations("upload");
  const { jobs, enqueue, busy } = useUploadQueue(workspaceId);
  const workspace = useWorkspace(workspaceId);
  const [demoError, setDemoError] = useState(false);
  const demoStarted = useRef(false);
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (!demo || demoStarted.current) return;
    demoStarted.current = true;
    // Drop the flag from the URL so a refresh does not upload the sample files again.
    router.replace(pathname);
    fetchDemoFiles().then(enqueue, () => setDemoError(true));
  }, [demo, enqueue, router, pathname]);

  const finished = jobs.length > 0 && !busy;
  const done = jobs.filter((j) => j.status === "done" && j.result);
  const records = done.reduce((n, j) => n + j.result!.tables.reduce((m, tb) => m + tb.rows_imported, 0), 0);
  const duplicates = done.reduce((n, j) => n + j.result!.tables.reduce((m, tb) => m + tb.duplicates, 0), 0);
  const datasetId = done[0]?.result?.tables[0]?.dataset_id;
  const pending = workspace.data?.pending_matches ?? 0;

  return (
    <div className="mx-auto max-w-5xl">
      <header className="mb-8">
        <h1 className="display text-3xl font-semibold sm:text-4xl">{t("title")}</h1>
        <p className="mt-2 max-w-2xl text-ink-muted">{t("lead")}</p>
      </header>

      {demo ? (
        <div className="mb-6 flex items-center gap-3 rounded-xl border border-accent/30 bg-accent-soft px-4 py-3 text-sm text-accent">
          <Sparkles className="size-4 shrink-0" />
          {t("demoBanner")}
        </div>
      ) : null}
      {demoError ? <ErrorState title={t("errors.network")} /> : null}

      <Dropzone onFiles={enqueue} compact={jobs.length > 0} />

      {jobs.length > 0 ? (
        <div className="mt-8 flex flex-col gap-4">
          {jobs.map((job) => (
            <JobCard key={job.id} job={job} workspaceId={workspaceId} />
          ))}
        </div>
      ) : null}

      {finished && done.length > 0 ? (
        <div className="sticky bottom-20 z-20 mt-8 flex flex-col gap-3 rounded-2xl border border-rule bg-paper-raised/95 p-4 shadow-card backdrop-blur animate-fade-up md:bottom-6 md:flex-row md:items-center md:justify-between">
          <p className="text-sm text-ink-muted tnum">
            {t("summary", { files: done.length, records, duplicates })}
          </p>
          <div className="flex flex-wrap gap-2">
            {pending > 0 ? (
              <Button asChild>
                <Link href={`/w/${workspaceId}/eslestirme`}>
                  <GitMerge />
                  {t("goMatching", { count: pending })}
                </Link>
              </Button>
            ) : null}
            {datasetId ? (
              <Button asChild variant={pending > 0 ? "secondary" : "primary"}>
                <Link href={`/w/${workspaceId}/veri/${datasetId}`}>
                  <Table2 />
                  {t("goTable")}
                </Link>
              </Button>
            ) : null}
            <Button asChild variant="ghost">
              <Link href={`/w/${workspaceId}`}>
                {t("goWorkspace")}
                <ArrowRight />
              </Link>
            </Button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
