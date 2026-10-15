"use client";

import {
  AlertTriangle,
  ArrowRight,
  BookOpen,
  CheckCircle2,
  Copy,
  Database,
  EyeOff,
  FileSpreadsheet,
  Loader2,
  Rows3,
  Users,
  Wand2,
  type LucideIcon,
} from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import Link from "next/link";
import { useTranslations } from "next-intl";

import { Badge } from "@/components/ui/badge";
import { ScoreRing } from "@/components/ui/misc";
import type { PipelineEvent } from "@/lib/api/stream";
import { KNOWN_ROLES, KNOWN_TRANSFORMS, RoleIcon } from "@/lib/roles";
import { useCountUp, usePacedCount } from "@/lib/use-animated";
import { cn, formatBytes } from "@/lib/utils";

import type { UploadJob } from "./use-upload-queue";

type Params = Record<string, unknown>;
const num = (p: Params, key: string) => Number(p[key] ?? 0);
const str = (p: Params, key: string) => String(p[key] ?? "");

const SKIP_REASONS = new Set(["title", "total", "empty", "repeated_header"]);
const ENCODINGS = new Set(["utf-8", "utf-8-sig", "utf-16", "cp1254", "iso-8859-9", "utf-8-lossy"]);
const ERRORS = new Set([
  "corrupt_excel",
  "legacy_xls",
  "unsupported_extension",
  "empty_file",
  "no_data_sheets",
  "too_large",
  "internal_error",
  "network",
]);

export function JobCard({ job, workspaceId }: { job: UploadJob; workspaceId: number }) {
  const t = useTranslations("upload");
  const columns = job.events.filter((e) => e.code === "column_recognized");
  const feed = job.events.filter((e) => e.code !== "column_recognized" && e.code !== "file_received");
  // Columns first (the satisfying part), then the rest of the story.
  const shownColumns = usePacedCount(columns.length, 220);
  const shownFeed = usePacedCount(shownColumns >= columns.length ? feed.length : 0, 260);
  const settled = job.status === "done" && shownFeed >= feed.length;

  const table = job.result?.tables[0];
  const totals = (job.result?.tables ?? []).reduce(
    (acc, t2) => ({
      records: acc.records + t2.rows_imported,
      duplicates: acc.duplicates + t2.duplicates,
      fixes: acc.fixes + Object.entries(t2.transforms).reduce(
        (n, [kind, count]) => (kind === "duplicate_removed" || kind === "text_trimmed" ? n : n + count),
        0,
      ),
    }),
    { records: 0, duplicates: 0, fixes: 0 },
  );

  return (
    <motion.article
      layout
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      className="overflow-hidden rounded-2xl border border-rule bg-paper-raised shadow-card"
    >
      <header className="flex items-center gap-3 border-b border-rule px-5 py-4">
        <FileSpreadsheet className="size-5 shrink-0 text-ink-faint" />
        <div className="min-w-0 flex-1">
          <p className="truncate font-medium">{job.file.name}</p>
          <p className="text-xs text-ink-faint tnum">{formatBytes(job.file.size)}</p>
        </div>
        <StatusPill status={settled || job.status !== "done" ? job.status : "processing"} />
      </header>

      {job.status === "failed" ? (
        <div role="alert" className="flex gap-3 px-5 py-4 text-sm">
          <AlertTriangle className="mt-0.5 size-4 shrink-0 text-bad" />
          <p className="text-ink-muted">
            {t(`errors.${ERRORS.has(job.error ?? "") ? (job.error as "internal_error") : "internal_error"}`)}
          </p>
        </div>
      ) : null}

      {job.status !== "queued" && job.status !== "failed" ? (
        <div className="grid gap-6 px-5 py-5 lg:grid-cols-[1fr_1.1fr]">
          <section aria-live="polite">
            <ul className="flex flex-col gap-2.5">
              <AnimatePresence initial={false}>
                {feed.slice(0, shownFeed).map((event, i) => (
                  <FeedLine key={`${event.code}-${i}`} event={event} />
                ))}
              </AnimatePresence>
              {!settled ? (
                <li className="flex items-center gap-2 text-sm text-ink-faint">
                  <Loader2 className="size-4 animate-spin" />
                  {t("processing")}
                </li>
              ) : null}
            </ul>
          </section>

          <section>
            <div className="flex flex-wrap gap-2">
              <AnimatePresence initial={false}>
                {columns.slice(0, shownColumns).map((event, i) => (
                  <ColumnChip key={i} params={event.params ?? {}} />
                ))}
              </AnimatePresence>
            </div>
            {settled ? (
              <motion.div
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                className="mt-6 grid grid-cols-3 gap-3"
              >
                <Stat value={totals.records} icon={CheckCircle2} label={t("stats.records")} />
                <Stat value={totals.fixes} icon={Wand2} label={t("stats.fixes")} />
                <Stat value={totals.duplicates} icon={Copy} label={t("stats.duplicates")} />
              </motion.div>
            ) : null}
          </section>
        </div>
      ) : null}

      {settled && job.result && table ? (
        <footer className="flex flex-wrap items-center justify-end gap-2 border-t border-rule bg-paper-sunken/50 px-5 py-3">
          <Link
            href={`/w/${workspaceId}/yuklemeler/${job.result.upload_id}`}
            className="inline-flex items-center gap-1.5 text-sm font-medium text-accent hover:underline"
          >
            {t("reviewFile")}
            <ArrowRight className="size-4" />
          </Link>
        </footer>
      ) : null}
    </motion.article>
  );
}

function StatusPill({ status }: { status: UploadJob["status"] }) {
  const t = useTranslations("upload");
  const tone = { queued: "neutral", processing: "accent", done: "ok", failed: "bad" } as const;
  return (
    <Badge tone={tone[status]}>
      {status === "processing" ? <Loader2 className="animate-spin" /> : null}
      {status === "done" ? <CheckCircle2 /> : null}
      {t(status)}
    </Badge>
  );
}

function ColumnChip({ params }: { params: Params }) {
  const tr = useTranslations("roles");
  const role = str(params, "role");
  const label = KNOWN_ROLES.has(role) ? tr(role as "party") : role;
  const header = str(params, "header");
  // Show the file's own header only when it says something different ("Kim" → Müşteri).
  const showHeader = header.toLocaleLowerCase("tr") !== label.toLocaleLowerCase("tr");
  return (
    <motion.div
      layout
      initial={{ opacity: 0, scale: 0.85, y: 10 }}
      animate={{ opacity: 1, scale: 1, y: 0 }}
      transition={{ type: "spring", stiffness: 420, damping: 28 }}
      className="flex items-center gap-2.5 rounded-xl border border-rule bg-paper py-1.5 pr-3 pl-1.5"
    >
      <ScoreRing value={num(params, "confidence")} size={32} />
      <div className="leading-tight">
        <p className="flex items-center gap-1.5 text-sm font-medium">
          <RoleIcon role={role} className="size-3.5 text-accent" />
          {label}
        </p>
        {showHeader ? (
          <p className="max-w-[10rem] truncate font-mono text-[11px] text-ink-faint">{header}</p>
        ) : null}
      </div>
    </motion.div>
  );
}

function FeedLine({ event }: { event: PipelineEvent }) {
  const t = useTranslations("upload");
  const p: Params = event.params ?? {};
  let icon: LucideIcon = CheckCircle2;
  let text: string;
  let tone = "text-ink-muted";

  switch (event.code) {
    case "file_read": {
      icon = BookOpen;
      const encoding = str(p, "encoding");
      text = t("events.file_read", { sheets: num(p, "sheets") });
      if (encoding && ENCODINGS.has(encoding)) {
        text += ` · ${t("events.encoding", { name: t(`encodings.${encoding as "cp1254"}`) })}`;
      }
      break;
    }
    case "table_detected":
      icon = Rows3;
      text =
        p.header_row == null
          ? t("events.table_detected_noheader", { rows: num(p, "rows") })
          : t("events.table_detected", { header_row: num(p, "header_row"), rows: num(p, "rows") });
      break;
    case "rows_skipped": {
      icon = EyeOff;
      const reason = str(p, "reason");
      text = SKIP_REASONS.has(reason)
        ? t(`events.rows_skipped.${reason as "title"}`, { count: num(p, "count") })
        : reason;
      break;
    }
    case "dataset_created":
    case "dataset_matched":
      icon = Database;
      text = t(`events.${event.code}`);
      break;
    case "values_normalized": {
      icon = Wand2;
      const kind = str(p, "kind");
      if (kind === "parse_failed") tone = "text-warn";
      text = KNOWN_TRANSFORMS.has(kind)
        ? t(`events.values_normalized.${kind as "date_parsed"}`, { count: num(p, "count") })
        : kind;
      break;
    }
    case "duplicates_removed":
      icon = Copy;
      tone = "text-ink";
      text = t("events.duplicates_removed", { count: num(p, "count") });
      break;
    case "entities_resolved":
      icon = Users;
      tone = "text-ink";
      text = t("events.entities_resolved", { entities: num(p, "entities") });
      if (num(p, "pending") > 0) text += ` · ${t("events.entities_pending", { pending: num(p, "pending") })}`;
      break;
    case "done":
      icon = CheckCircle2;
      tone = "text-ok font-medium";
      text = t("events.done", { rows: num(p, "rows") });
      break;
    default:
      text = event.code;
  }
  const Icon = icon;
  return (
    <motion.li
      initial={{ opacity: 0, x: -8 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ duration: 0.25 }}
      className={cn("flex items-start gap-2.5 text-sm", tone)}
    >
      <Icon className="mt-0.5 size-4 shrink-0 text-accent" />
      <span>{text}</span>
    </motion.li>
  );
}

function Stat({ value, icon: Icon, label }: { value: number; icon: LucideIcon; label: string }) {
  const shown = useCountUp(value);
  return (
    <div className="rounded-xl border border-rule bg-paper px-3 py-2.5">
      <Icon className="size-4 text-accent" />
      <p className="display mt-1 text-2xl font-semibold tnum">{shown.toLocaleString("tr-TR")}</p>
      <p className="text-xs text-ink-muted">{label}</p>
    </div>
  );
}
