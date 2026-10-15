"use client";

import { GitMerge, History, RotateCcw, Undo2, Upload, type LucideIcon } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { useTransformLabel } from "@/components/transform-detail";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState, ErrorState, Skeleton } from "@/components/ui/misc";
import { ConfirmDialog } from "@/components/ui/sheet";
import type { Schemas } from "@/lib/api/client";
import { useRestore, useVersions } from "@/lib/api/hooks";
import { cn, formatDateTime } from "@/lib/utils";

type Version = Schemas["VersionItem"];

const ICONS: Record<string, LucideIcon> = {
  upload: Upload,
  match_decision: GitMerge,
  undo: Undo2,
  restore: RotateCcw,
};
const dayFormat = new Intl.DateTimeFormat("tr-TR", { day: "numeric", month: "long", year: "numeric" });

export function HistoryView({ ws }: { ws: number }) {
  const t = useTranslations("history");
  const tc = useTranslations("common");
  const versions = useVersions(ws);
  const restore = useRestore(ws);
  const [target, setTarget] = useState<Version | null>(null);

  if (versions.isError) return <ErrorState title={tc("error")} onRetry={() => versions.refetch()} retryLabel={tc("retry")} />;

  const groups = new Map<string, Version[]>();
  for (const v of versions.data ?? []) {
    const day = dayFormat.format(new Date(v.created_at));
    groups.set(day, [...(groups.get(day) ?? []), v]);
  }

  return (
    <div className="mx-auto max-w-3xl">
      <header className="mb-8">
        <h1 className="display text-3xl font-semibold sm:text-4xl">{t("title")}</h1>
        <p className="mt-2 text-ink-muted">{t("lead")}</p>
      </header>

      {versions.isPending ? (
        <div className="flex flex-col gap-3">
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-16 rounded-xl" />
          ))}
        </div>
      ) : versions.data?.length === 0 ? (
        <EmptyState icon={<History />} title={t("empty")} />
      ) : (
        [...groups.entries()].map(([day, items]) => (
          <section key={day} className="mb-8">
            <h2 className="mb-3 text-sm font-medium text-ink-faint">{day}</h2>
            <ol className="relative border-l border-rule pl-6">
              {items.map((v) => (
                <VersionRow key={v.id} version={v} onRestore={() => setTarget(v)} />
              ))}
            </ol>
          </section>
        ))
      )}

      <ConfirmDialog
        open={target !== null}
        onOpenChange={(open) => !open && setTarget(null)}
        title={t("restoreTitle")}
        body={target ? t("restoreBody", { date: formatDateTime(target.created_at) }) : ""}
        confirmLabel={t("restore")}
        busy={restore.isPending}
        onConfirm={() => target && restore.mutate(target.id, { onSuccess: () => setTarget(null) })}
      />
    </div>
  );
}

function VersionRow({ version, onRestore }: { version: Version; onRestore: () => void }) {
  const t = useTranslations("history");
  const Icon = ICONS[version.kind] ?? History;
  const time = new Date(version.created_at).toLocaleTimeString("tr-TR", { hour: "2-digit", minute: "2-digit" });
  return (
    <li className="relative mb-4 last:mb-0">
      <span
        className={cn(
          "absolute top-3 -left-[37px] grid size-6 place-items-center rounded-full border bg-paper-raised",
          version.is_current ? "border-accent text-accent" : "border-rule-strong text-ink-faint",
        )}
      >
        <Icon className="size-3.5" />
      </span>
      <div
        className={cn(
          "flex flex-col gap-2 rounded-xl border bg-paper-raised px-4 py-3 sm:flex-row sm:items-center",
          version.is_current ? "border-accent/40" : "border-rule",
        )}
      >
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium">
            <VersionTitle version={version} />
          </p>
          <p className="mt-0.5 text-xs text-ink-faint tnum">
            {time} · #{version.id}
            {version.added || version.removed || version.changed
              ? ` · ${t("counts", { added: version.added, removed: version.removed, changed: version.changed })}`
              : ""}
          </p>
        </div>
        {version.is_current ? (
          <Badge tone="accent">{t("current")}</Badge>
        ) : (
          <Button variant="ghost" size="sm" onClick={onRestore} className="self-start sm:self-auto">
            <RotateCcw />
            {t("restore")}
          </Button>
        )}
      </div>
    </li>
  );
}

/** Versions written before structured details existed carry only an English message. */
function legacyDetails(version: Version): Record<string, string> {
  const message = version.message ?? "";
  if (version.kind === "upload") return { filename: message };
  if (version.kind === "match_decision") {
    const m = /^(same|different|skip): (.*?)\|\S* ~ (.*?)\|/.exec(message);
    return m ? { decision: m[1]!, a: m[2]!, b: m[3]! } : {};
  }
  if (version.kind === "undo") {
    if (message.startsWith("undo upload ")) return { target: "upload", filename: message.slice(12) };
    if (message.startsWith("undo decision")) return { target: "decision" };
    const m = /^undo (\w+) #/.exec(message);
    return m ? { target: "transformation", kind: m[1]! } : {};
  }
  return {};
}

function VersionTitle({ version }: { version: Version }) {
  const t = useTranslations("history.kinds");
  const label = useTransformLabel();
  const d = { ...legacyDetails(version), ...(version.details as Record<string, string | number | null>) };
  const s = (key: string) => String(d[key] ?? "?");
  switch (version.kind) {
    case "upload":
      return <>{t("upload", { filename: s("filename") })}</>;
    case "match_decision": {
      const decision = s("decision");
      if (decision === "same" || decision === "different" || decision === "skip") {
        return <>{t(`match_decision.${decision}`, { a: s("a"), b: s("b") })}</>;
      }
      break;
    }
    case "undo": {
      const target = s("target");
      if (target === "decision") return <>{t("undo.decision")}</>;
      if (target === "transformation") return <>{t("undo.transformation", { kind: label(s("kind")) })}</>;
      if (target === "upload") return <>{t("undo.upload", { filename: s("filename") })}</>;
      break;
    }
    case "restore":
      return <>{t("restore", { version: s("to") })}</>;
  }
  return <>{t("unknown", { message: version.message ?? version.kind })}</>;
}
