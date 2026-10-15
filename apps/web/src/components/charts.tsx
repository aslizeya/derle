"use client";

import { useTranslations } from "next-intl";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { cn, formatMoney } from "@/lib/utils";

/** Validated categorical order (see globals.css): series colour follows the entity, never rank. */
export const SERIES_COLORS = ["var(--series-1)", "var(--series-2)"] as const;

const compactMoney = new Intl.NumberFormat("tr-TR", {
  style: "currency",
  currency: "TRY",
  notation: "compact",
  maximumFractionDigits: 1,
});
const monthFormat = new Intl.DateTimeFormat("tr-TR", { month: "short", year: "2-digit", timeZone: "UTC" });

export function formatMonth(value: string): string {
  const date = new Date(`${value}-01T00:00:00Z`);
  return Number.isNaN(date.getTime()) ? value : monthFormat.format(date);
}

export type Series = { key: string; label: string };

export function Legend({ series }: { series: Series[] }) {
  if (series.length < 2) return null;
  return (
    <ul className="flex flex-wrap gap-4 text-xs text-ink-muted">
      {series.map((s, i) => (
        <li key={s.key} className="flex items-center gap-1.5">
          <span className="size-2.5 rounded-sm" style={{ background: SERIES_COLORS[i] }} aria-hidden />
          {s.label}
        </li>
      ))}
    </ul>
  );
}

type TooltipProps = {
  active?: boolean;
  payload?: ReadonlyArray<{ dataKey?: unknown; value?: unknown }>;
  label?: unknown;
  series: Series[];
};

function ChartTooltip({ active, payload, label, series }: TooltipProps) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border border-rule bg-paper-raised px-3 py-2 text-xs shadow-card">
      <p className="mb-1 font-medium text-ink">{formatMonth(String(label))}</p>
      {payload.map((item) => {
        const index = series.findIndex((s) => s.key === item.dataKey);
        return (
          <p key={String(item.dataKey)} className="flex items-center gap-2 text-ink-muted">
            <span className="size-2 rounded-sm" style={{ background: SERIES_COLORS[index] }} aria-hidden />
            <span className="flex-1">{series[index]?.label}</span>
            <span className="font-medium text-ink tnum">{formatMoney(Number(item.value))}</span>
          </p>
        );
      })}
    </div>
  );
}

/** Columns over time (months). One shared baseline, one y-axis, at most two series. */
export function ColumnChart({
  rows,
  x,
  series,
  height = 260,
}: {
  rows: Record<string, unknown>[];
  x: string;
  series: Series[];
  height?: number;
}) {
  return (
    <div className="flex flex-col gap-3">
      <Legend series={series} />
      <div style={{ height }} className="-ml-2">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={rows} barGap={2} barCategoryGap="28%" margin={{ top: 8, right: 8, bottom: 0, left: 8 }}>
            <CartesianGrid vertical={false} stroke="var(--grid)" />
            <XAxis
              dataKey={x}
              tickFormatter={formatMonth}
              tickLine={false}
              axisLine={{ stroke: "var(--rule-strong)" }}
              tick={{ fill: "var(--ink-faint)", fontSize: 12 }}
            />
            <YAxis
              tickFormatter={(v: number) => compactMoney.format(v)}
              tickLine={false}
              axisLine={false}
              width={64}
              tick={{ fill: "var(--ink-faint)", fontSize: 12 }}
            />
            <Tooltip
              cursor={{ fill: "var(--paper-sunken)" }}
              content={(props) => <ChartTooltip {...props} series={series} />}
            />
            {series.map((s, i) => (
              <Bar
                key={s.key}
                dataKey={s.key}
                name={s.label}
                fill={SERIES_COLORS[i]}
                radius={[4, 4, 0, 0]}
                maxBarSize={24}
                isAnimationActive={false}
              />
            ))}
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

/**
 * Ranked horizontal bars as plain HTML: names stay fully readable on phones and every value
 * is labelled at the bar tip, so no tooltip is needed to read it.
 */
export function RankedBars({
  rows,
  label,
  value,
  format = formatMoney,
}: {
  rows: Record<string, unknown>[];
  label: string;
  value: string;
  format?: (v: number) => string;
}) {
  const max = Math.max(...rows.map((r) => Math.abs(Number(r[value]) || 0)), 1);
  return (
    <ol className="flex flex-col gap-2.5">
      {rows.map((row, i) => {
        const v = Number(row[value]) || 0;
        return (
          <li key={`${String(row[label])}-${i}`} className="grid grid-cols-[minmax(0,9rem)_1fr] items-center gap-3 text-sm sm:grid-cols-[minmax(0,12rem)_1fr]">
            <span className="truncate text-ink" title={String(row[label])}>
              {String(row[label] ?? "—")}
            </span>
            <span className="flex items-center gap-2">
              <span
                className="h-3.5 rounded-r-[4px] bg-series-1"
                style={{ width: `${Math.max((Math.abs(v) / max) * 100, 1.5)}%` }}
                aria-hidden
              />
              <span className="shrink-0 text-xs text-ink-muted tnum">{format(v)}</span>
            </span>
          </li>
        );
      })}
    </ol>
  );
}

/** Accessible fallback: the same data as a table. */
export function DataTable({
  columns,
  rows,
  formatters = {},
  className,
}: {
  columns: { key: string; label: string; numeric?: boolean }[];
  rows: Record<string, unknown>[];
  formatters?: Record<string, (v: unknown) => string>;
  className?: string;
}) {
  const t = useTranslations("common");
  return (
    <div className={cn("overflow-x-auto rounded-xl border border-rule", className)}>
      <table className="w-full text-sm">
        <thead className="bg-paper-sunken/50 text-left text-xs text-ink-muted">
          <tr>
            {columns.map((c) => (
              <th key={c.key} className={cn("px-3 py-2 font-medium", c.numeric && "text-right")}>
                {c.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i} className="border-t border-rule/60">
              {columns.map((c) => {
                const raw = row[c.key];
                const fmt = formatters[c.key];
                return (
                  <td key={c.key} className={cn("px-3 py-1.5", c.numeric && "text-right tnum")}>
                    {raw === null || raw === undefined ? t("empty") : fmt ? fmt(raw) : String(raw)}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
