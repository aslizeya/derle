"use client";

import { ArrowUp, Bot, Clock, Loader2, MessageCircleQuestion, ShieldCheck, Sparkles, Table2 } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { useTranslations } from "next-intl";
import { type FormEvent, useState } from "react";

import { ColumnChart, DataTable, RankedBars, formatMonth } from "@/components/charts";
import { DatasetSelect, useActiveDataset } from "@/components/dataset-select";
import { SqlBlock } from "@/components/sql-block";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { Schemas } from "@/lib/api/client";
import { useAsk, useRecentQuestions } from "@/lib/api/hooks";
import { cn, formatDate, formatMoney, formatNumber } from "@/lib/utils";

type Answer = Schemas["Answer"];

const MONEY_METRICS = new Set(["sales", "payments", "balance"]);
const ERROR_CODES = new Set([
  "not_understood", "llm_no_answer", "customer_not_found", "no_money", "no_payments",
  "no_dates", "no_customers", "no_data", "timeout", "execution_failed",
]);

export function AskView({ ws }: { ws: number }) {
  const t = useTranslations("ask");
  const { active, setPicked } = useActiveDataset(ws);
  const ask = useAsk(ws);
  const recent = useRecentQuestions(ws);
  const [question, setQuestion] = useState("");
  const [answers, setAnswers] = useState<Answer[]>([]);
  const examples = t.raw("exampleList") as string[];

  function submit(text: string) {
    const q = text.trim();
    if (q.length < 2 || ask.isPending) return;
    setQuestion("");
    ask.mutate(
      { question: q, datasetId: active?.id },
      { onSuccess: (answer) => setAnswers((all) => [answer, ...all]) },
    );
  }

  return (
    <div className="mx-auto max-w-6xl">
      <header className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="display text-3xl font-semibold sm:text-4xl">{t("title")}</h1>
          <p className="mt-2 max-w-2xl text-ink-muted">{t("lead")}</p>
        </div>
        <DatasetSelect ws={ws} value={active?.id} onChange={setPicked} />
      </header>

      <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_260px]">
        <div className="min-w-0">
          <form
            onSubmit={(e: FormEvent) => {
              e.preventDefault();
              submit(question);
            }}
            className="ruled flex items-center gap-2 rounded-2xl border border-rule-strong py-2 pr-2 pl-14 shadow-card focus-within:border-accent sm:pl-16"
          >
            <input
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder={t("placeholder")}
              aria-label={t("placeholder")}
              maxLength={300}
              className="h-12 min-w-0 flex-1 bg-transparent text-lg text-ink placeholder:text-ink-faint focus:outline-none"
            />
            <Button type="submit" size="icon" className="size-11 rounded-xl" disabled={ask.isPending || question.trim().length < 2} aria-label={t("submit")}>
              {ask.isPending ? <Loader2 className="animate-spin" /> : <ArrowUp />}
            </Button>
          </form>

          <div className="mt-3 flex flex-wrap gap-2">
            {examples.map((ex) => (
              <button
                key={ex}
                type="button"
                onClick={() => submit(ex)}
                disabled={ask.isPending}
                className="rounded-full border border-rule bg-paper-raised px-3 py-1.5 text-sm text-ink-muted transition-colors hover:border-accent/50 hover:text-ink disabled:opacity-50"
              >
                {ex}
              </button>
            ))}
          </div>

          <div className="mt-8 flex flex-col gap-5">
            {ask.isPending ? (
              <div className="flex items-center gap-3 rounded-2xl border border-dashed border-rule-strong px-5 py-6 text-sm text-ink-muted">
                <Loader2 className="size-4 animate-spin text-accent" />
                {t("thinking")}
              </div>
            ) : null}
            <AnimatePresence initial={false}>
              {answers.map((answer, i) => (
                <motion.div
                  key={`${answers.length - i}`}
                  initial={{ opacity: 0, y: 12 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.25 }}
                >
                  <AnswerCard answer={answer} />
                </motion.div>
              ))}
            </AnimatePresence>
          </div>
        </div>

        <aside>
          <h2 className="mb-3 flex items-center gap-2 text-sm font-medium text-ink-muted">
            <Clock className="size-4" />
            {t("recent")}
          </h2>
          <ul className="flex flex-col gap-1">
            {recent.data?.map((r) => (
              <li key={r.question}>
                <button
                  type="button"
                  onClick={() => submit(r.question)}
                  className={cn(
                    "w-full rounded-lg px-3 py-2 text-left text-sm hover:bg-paper-sunken",
                    r.ok ? "text-ink" : "text-ink-faint line-through decoration-ink-faint/40",
                  )}
                >
                  {r.question}
                </button>
              </li>
            ))}
          </ul>
        </aside>
      </div>
    </div>
  );
}

function useAnswerFormat(answer: Answer) {
  const metric = answer.explanation?.metric as string | undefined;
  const money = metric ? MONEY_METRICS.has(metric) : false;
  return (column: string, value: unknown): string => {
    if (value === null || value === undefined) return "—";
    if (column === "Ay") return formatMonth(String(value));
    if (column === "Gün") return formatDate(String(value));
    if (typeof value === "number") {
      const isMeasure = answer.columns.indexOf(column) === answer.columns.length - 1;
      return money && isMeasure ? formatMoney(value) : formatNumber(value);
    }
    return String(value);
  };
}

function AnswerCard({ answer }: { answer: Answer }) {
  const t = useTranslations("ask");
  const td = useTranslations("dashboard");
  const format = useAnswerFormat(answer);
  const [asTable, setAsTable] = useState(false);
  const rows = answer.rows.map((r) => Object.fromEntries(answer.columns.map((c, i) => [c, r[i]])));
  const measure = answer.columns[answer.columns.length - 1];
  const label = answer.columns.length > 1 ? answer.columns[0] : undefined;

  if (answer.error) {
    const code = answer.error.startsWith("rejected_") ? "rejected" : answer.error;
    const params = (answer.error_params ?? {}) as Record<string, string>;
    return (
      <article className="rounded-2xl border border-warn/30 bg-warn-soft/60 p-5">
        <p className="display text-lg font-semibold">{answer.question}</p>
        <p className="mt-2 flex gap-2 text-sm text-ink-muted">
          <MessageCircleQuestion className="mt-0.5 size-4 shrink-0 text-warn" />
          {ERROR_CODES.has(code) || code === "rejected" ? t(`errors.${code as "not_understood"}`, params as { name: string }) : code}
        </p>
        {answer.sql ? <div className="mt-4"><SqlBlock sql={answer.sql} label={t("showSql")} /></div> : null}
      </article>
    );
  }

  const single = answer.chart === "kpi" && rows.length === 1 && measure;
  const top = !single && label && measure && rows[0] ? rows[0] : null;

  return (
    <article className="rounded-2xl border border-rule bg-paper-raised p-5 shadow-card">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <p className="display text-lg font-semibold">{answer.question}</p>
        <div className="flex items-center gap-2">
          <Badge tone={answer.engine === "llm" ? "accent" : "outline"}>
            {answer.engine === "llm" ? <Sparkles /> : <Bot />}
            {t(`engine.${answer.engine}`)}
          </Badge>
          <span className="text-xs text-ink-faint tnum">{t("duration", { ms: answer.duration_ms })}</span>
        </div>
      </div>

      <Explanation answer={answer} />

      {single ? (
        <p className="mt-5 text-5xl font-semibold tracking-tight tnum">{format(measure, rows[0]![measure])}</p>
      ) : top ? (
        <p className="mt-4 text-sm text-ink-muted">
          {t("answer")}:{" "}
          <span className="text-base font-semibold text-ink">{format(label!, top[label!])}</span>
          <span className="ml-2 tnum">{format(measure!, top[measure!])}</span>
        </p>
      ) : null}

      {!single && rows.length > 0 ? (
        <div className="mt-5">
          <div className="mb-3 flex items-center justify-between">
            <span className="text-xs text-ink-faint">
              {answer.truncated ? t("truncated", { count: rows.length }) : t("rows", { count: rows.length })}
            </span>
            {answer.chart !== "table" ? (
              <button
                type="button"
                onClick={() => setAsTable((v) => !v)}
                className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs text-ink-muted hover:bg-paper-sunken hover:text-ink"
              >
                <Table2 className="size-3.5" />
                {asTable ? td("hideTable") : td("showTable")}
              </button>
            ) : null}
          </div>
          {answer.chart === "bar" && !asTable && label && measure ? (
            <RankedBars rows={rows} label={label} value={measure} format={(v) => format(measure, v)} />
          ) : answer.chart === "column" && !asTable && label && measure ? (
            <ColumnChart rows={rows} x={label} series={[{ key: measure, label: measure }]} height={220} />
          ) : (
            <DataTable
              columns={answer.columns.map((c, i) => ({ key: c, label: c, numeric: typeof answer.rows[0]?.[i] === "number" }))}
              rows={rows}
              formatters={Object.fromEntries(answer.columns.map((c) => [c, (v: unknown) => format(c, v)]))}
            />
          )}
        </div>
      ) : null}

      {answer.sql ? (
        <div className="mt-5">
          <SqlBlock
            sql={answer.sql}
            label={t("showSql")}
            note={t("readOnly")}
          />
        </div>
      ) : null}
      {answer.llm_explanation ? <p className="mt-3 text-xs text-ink-faint">{answer.llm_explanation}</p> : null}
    </article>
  );
}

function Explanation({ answer }: { answer: Answer }) {
  const ta = useTranslations("ask");
  const t = (key: string, values?: Record<string, string>) =>
    ta(`explain.${key}` as "explain.average", values as never);
  const e = answer.explanation as
    | {
        metric?: string;
        aggregate?: string;
        group?: string | null;
        order?: string;
        period?: { start: string; end: string };
        customer?: { name: string };
      }
    | null
    | undefined;
  if (!e) return null;
  const chips: string[] = [];
  if (e.aggregate === "avg") chips.push(t("average"));
  if (e.metric) chips.push(t(`metric.${e.metric as "sales"}`));
  if (e.group) chips.push(t(`group.${e.group as "customer"}`));
  if (e.order) chips.push(t(`order.${e.order as "desc"}`));
  if (e.period) chips.push(t("period", { start: formatDate(e.period.start), end: formatDate(e.period.end) }));
  if (e.customer) chips.push(t("customer", { name: e.customer.name }));
  const stale = answer.anchor?.reason === "data_end" && e.period;
  return (
    <div className="mt-3">
      <div className="flex flex-wrap gap-1.5">
        {chips.map((c) => (
          <Badge key={c} tone="neutral">{c}</Badge>
        ))}
        <Badge tone="ok" className="ml-auto">
          <ShieldCheck />
          {ta("readOnlyShort")}
        </Badge>
      </div>
      {stale ? (
        <p className="mt-2 text-xs text-ink-faint">{ta("anchorNote", { date: formatDate(answer.anchor?.date ?? "") })}</p>
      ) : null}
    </div>
  );
}
