"use client";

import { AlertTriangle, ArrowRight, CheckCircle2, Info, OctagonAlert, type LucideIcon } from "lucide-react";
import Link from "next/link";
import { useTranslations } from "next-intl";

import { Badge } from "@/components/ui/badge";
import { ErrorState, Skeleton } from "@/components/ui/misc";
import type { Schemas } from "@/lib/api/client";
import { useDataset, useQuality } from "@/lib/api/hooks";
import { cn, formatMoney } from "@/lib/utils";

type Issue = Schemas["QualityIssue"];

const SEVERITY: Record<Issue["severity"], { icon: LucideIcon; tone: "bad" | "warn" | "neutral" }> = {
  serious: { icon: OctagonAlert, tone: "bad" },
  warning: { icon: AlertTriangle, tone: "warn" },
  info: { icon: Info, tone: "neutral" },
};
const ISSUE_CODES = new Set([
  "missing_values", "unreadable_values", "pending_matches", "uncertain_values", "outliers", "future_dates",
]);  // prettier-ignore

/** Big score ring; status colours carry an icon/label too, never colour alone. */
export function QualityScore({ score, grade, size = 120 }: { score: number; grade: string; size?: number }) {
  const t = useTranslations("quality");
  const stroke = size > 80 ? 8 : 5;
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const color = score >= 90 ? "var(--ok)" : score >= 75 ? "var(--accent)" : score >= 50 ? "var(--warn)" : "var(--bad)";
  return (
    <div className="relative grid place-items-center" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90" aria-hidden>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--rule)" strokeWidth={stroke} />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke={color}
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={c}
          strokeDashoffset={c * (1 - score / 100)}
        />
      </svg>
      <div className="absolute text-center leading-none">
        <span className={cn("font-semibold tnum", size > 80 ? "text-4xl" : "text-sm")}>{score}</span>
        {size > 80 ? <p className="mt-1 text-xs text-ink-muted">{t(`grades.${grade as "good"}`)}</p> : null}
      </div>
    </div>
  );
}

export function QualityView({ ws, datasetId }: { ws: number; datasetId: number }) {
  const t = useTranslations("quality");
  const tc = useTranslations("common");
  const report = useQuality(datasetId);
  const dataset = useDataset(datasetId);

  if (report.isError) return <ErrorState title={tc("error")} onRetry={() => report.refetch()} retryLabel={tc("retry")} />;
  const data = report.data;

  return (
    <div className="mx-auto max-w-4xl">
      <header className="mb-8">
        <p className="text-sm text-ink-faint">{dataset.data?.name}</p>
        <h1 className="display mt-1 text-3xl font-semibold sm:text-4xl">{t("title")}</h1>
      </header>

      {!data ? (
        <Skeleton className="h-64 rounded-2xl" />
      ) : data.score === null || data.grade === null ? (
        <p className="text-ink-muted">{t("empty")}</p>
      ) : (
        <>
          <section className="flex flex-col items-start gap-6 rounded-2xl border border-rule bg-paper-raised p-6 sm:flex-row sm:items-center">
            <QualityScore score={data.score} grade={data.grade} />
            <div>
              <p className="text-sm font-medium text-ink-muted">{t("score")}</p>
              <p className="mt-2 max-w-xl text-sm leading-relaxed text-ink-muted">{t("lead")}</p>
              {data.notes.map((n) => (
                <p key={n.code} className="mt-3 flex items-center gap-2 text-sm text-ok">
                  <CheckCircle2 className="size-4" />
                  {t("notes.duplicates_removed", { count: n.count })}
                </p>
              ))}
            </div>
          </section>

          <section className="mt-6 flex flex-col gap-3">
            {data.issues.length === 0 ? (
              <p className="flex items-center gap-2 rounded-2xl border border-ok/30 bg-ok-soft px-5 py-4 text-sm">
                <CheckCircle2 className="size-4 text-ok" />
                {t("noIssues")}
              </p>
            ) : (
              data.issues.map((issue, i) => <IssueCard key={`${issue.code}-${i}`} issue={issue} ws={ws} datasetId={datasetId} />)
            )}
          </section>

          <section className="mt-10">
            <h2 className="mb-4 font-semibold">{t("fields")}</h2>
            <ul className="flex flex-col gap-2">
              {data.fields.map((f) => (
                <li key={f.key} className="grid grid-cols-[minmax(0,10rem)_1fr_3.5rem] items-center gap-3 text-sm">
                  <span className="truncate">{f.label}</span>
                  <span className="h-2 overflow-hidden rounded-full bg-paper-sunken">
                    <span className="block h-full rounded-full bg-series-1" style={{ width: `${f.ratio * 100}%` }} />
                  </span>
                  <span className="text-right text-xs text-ink-muted tnum">%{Math.round(f.ratio * 100)}</span>
                </li>
              ))}
            </ul>
          </section>
        </>
      )}
    </div>
  );
}

function IssueCard({ issue, ws, datasetId }: { issue: Issue; ws: number; datasetId: number }) {
  const t = useTranslations("quality");
  const known = ISSUE_CODES.has(issue.code);
  const { icon: Icon, tone } = SEVERITY[issue.severity];
  const p = issue.params as Record<string, unknown>;
  const field = p.field === "money" ? t("moneyField") : String(p.field ?? "");
  const code = issue.code as "outliers";
  const title = known ? t(`issues.${code}`, { count: issue.count, field }) : issue.code;
  const examples = Array.isArray(p.examples) ? p.examples.map((v) => formatMoney(Number(v))).join(", ") : "";
  const fix = known ? t(`fixes.${code}`, { examples }) : "";
  const href = actionHref(issue.action as Record<string, unknown>, ws, datasetId);

  return (
    <article className="flex flex-col gap-3 rounded-2xl border border-rule bg-paper-raised p-5 sm:flex-row sm:items-start">
      <Icon className={cn("size-5 shrink-0", tone === "bad" ? "text-bad" : tone === "warn" ? "text-warn" : "text-ink-faint")} />
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <h3 className="font-semibold">{title}</h3>
          <Badge tone={tone}>{t(`severity.${issue.severity}`)}</Badge>
        </div>
        <p className="mt-1 text-sm text-ink-muted">{fix}</p>
        {issue.code === "uncertain_values" ? (
          <p className="mt-1 text-xs text-ink-faint tnum">
            {t("uncertainDetail", {
              year_inferred: Number(p.year_inferred ?? 0),
              ambiguous_order: Number(p.ambiguous_order ?? 0),
              ambiguous_number: Number(p.ambiguous_number ?? 0),
            })}
          </p>
        ) : null}
      </div>
      <div className="flex shrink-0 items-center gap-3">
        <span className="text-sm font-medium text-ink-muted tnum">{t("penalty", { value: issue.penalty.toLocaleString("tr-TR") })}</span>
        {href ? (
          <Link href={href} className="inline-flex items-center gap-1 text-sm font-medium text-accent hover:underline">
            {t("fix")}
            <ArrowRight className="size-4" />
          </Link>
        ) : null}
      </div>
    </article>
  );
}

function actionHref(action: Record<string, unknown>, ws: number, datasetId: number): string | null {
  switch (action.kind) {
    case "matching":
      return `/w/${ws}/eslestirme`;
    case "review":
      return action.upload_id ? `/w/${ws}/yuklemeler/${action.upload_id}` : `/w/${ws}`;
    case "table": {
      const params = new URLSearchParams();
      if (action.sort) params.set("sort", String(action.sort));
      if (action.desc) params.set("desc", "1");
      const query = params.toString();
      return `/w/${ws}/veri/${datasetId}${query ? `?${query}` : ""}`;
    }
    default:
      return null;
  }
}
