"use client";

import { BarChart3, Table2 } from "lucide-react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { ColumnChart, DataTable, RankedBars, formatMonth } from "@/components/charts";
import { DatasetSelect, useActiveDataset } from "@/components/dataset-select";
import { SqlBlock } from "@/components/sql-block";
import { Button } from "@/components/ui/button";
import { EmptyState, ErrorState, Skeleton } from "@/components/ui/misc";
import type { Schemas } from "@/lib/api/client";
import { useDashboard } from "@/lib/api/hooks";
import { formatDate, formatMoney } from "@/lib/utils";

type Chart = Schemas["Chart"];
type Kpi = Schemas["Kpi"];

const KPI_KEYS = new Set(["records", "customers", "sales", "payments", "open_balance", "period"]);
const CHART_KEYS = new Set(["monthly", "top_customers_open_balance", "top_customers_sales", "by_category"]);
const SERIES_KEYS = new Set(["sales", "payments", "open_balance"]);
const AXIS_KEYS = new Set(["month", "customer", "category"]);

export function DashboardView({ ws }: { ws: number }) {
  const t = useTranslations("dashboard");
  const tc = useTranslations("common");
  const tn = useTranslations("nav");
  const { datasets, active, setPicked } = useActiveDataset(ws);
  const dashboard = useDashboard(active?.id);

  if (datasets.data && datasets.data.length === 0) {
    return (
      <EmptyState icon={<BarChart3 />} title={t("empty")}>
        <Button asChild>
          <Link href={`/w/${ws}/yukle`}>{tn("upload")}</Link>
        </Button>
      </EmptyState>
    );
  }
  if (dashboard.isError) return <ErrorState title={tc("error")} onRetry={() => dashboard.refetch()} retryLabel={tc("retry")} />;

  const data = dashboard.data;
  const hero = data?.kpis.find((k) => k.key === "open_balance") ?? data?.kpis.find((k) => k.key === "sales");
  const others = data?.kpis.filter((k) => k !== hero) ?? [];

  return (
    <div className="mx-auto max-w-6xl">
      <header className="mb-8 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="display text-3xl font-semibold sm:text-4xl">{t("title")}</h1>
          <p className="mt-2 max-w-2xl text-ink-muted">{t("lead")}</p>
        </div>
        <DatasetSelect ws={ws} value={active?.id} onChange={setPicked} />
      </header>

      {!data ? (
        <div className="grid gap-4 sm:grid-cols-3">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-28 rounded-2xl" />
          ))}
          <Skeleton className="h-80 rounded-2xl sm:col-span-3" />
        </div>
      ) : (
        <>
          <section className="grid gap-3 lg:grid-cols-[1.3fr_2fr]">
            {hero ? <KpiTile kpi={hero} hero /> : null}
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
              {others.map((k) => (
                <KpiTile key={k.key} kpi={k} />
              ))}
            </div>
          </section>

          {data.charts.length === 0 ? (
            <p className="mt-8 text-sm text-ink-muted">{t("nothing")}</p>
          ) : (
            <div className="mt-6 grid gap-4 lg:grid-cols-2">
              {data.charts.map((chart) => (
                <ChartCard key={chart.key} chart={chart} wide={chart.kind === "column"} />
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}

function KpiTile({ kpi, hero = false }: { kpi: Kpi; hero?: boolean }) {
  const t = useTranslations("dashboard");
  const label = KPI_KEYS.has(kpi.key) ? t(`kpis.${kpi.key as "records"}`) : kpi.key;
  let value: string;
  if (kpi.format === "money") value = formatMoney(Number(kpi.value ?? 0));
  else if (kpi.format === "date_range" && Array.isArray(kpi.value)) {
    value = `${formatDate(String(kpi.value[0]))} – ${formatDate(String(kpi.value[1]))}`;
  } else value = Number(kpi.value ?? 0).toLocaleString("tr-TR");
  return (
    <div className={hero ? "rounded-2xl border border-rule bg-paper-raised p-6" : "rounded-2xl border border-rule bg-paper-raised p-4"}>
      <p className="text-sm text-ink-muted">{label}</p>
      <p
        className={
          hero
            ? "mt-2 text-5xl font-semibold tracking-tight text-ink tnum"
            : kpi.format === "date_range"
              ? "mt-1 text-sm font-semibold text-ink tnum"
              : "mt-1 text-2xl font-semibold text-ink tnum"
        }
      >
        {value}
      </p>
    </div>
  );
}

function ChartCard({ chart, wide }: { chart: Chart; wide: boolean }) {
  const t = useTranslations("dashboard");
  const [asTable, setAsTable] = useState(false);
  const title = CHART_KEYS.has(chart.key) ? t(`charts.${chart.key as "monthly"}`) : chart.key;
  const series = chart.series.map((key) => ({
    key,
    label: SERIES_KEYS.has(key) ? t(`series.${key as "sales"}`) : key,
  }));
  const xLabel = AXIS_KEYS.has(chart.x) ? t(`axis.${chart.x as "month"}`) : chart.x;

  return (
    <article className={wide ? "rounded-2xl border border-rule bg-paper-raised p-5 lg:col-span-2" : "rounded-2xl border border-rule bg-paper-raised p-5"}>
      <div className="mb-4 flex items-start justify-between gap-3">
        <h2 className="font-semibold">{title}</h2>
        <button
          type="button"
          onClick={() => setAsTable((v) => !v)}
          className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs text-ink-muted hover:bg-paper-sunken hover:text-ink"
        >
          {asTable ? <BarChart3 className="size-3.5" /> : <Table2 className="size-3.5" />}
          {asTable ? t("hideTable") : t("showTable")}
        </button>
      </div>
      {asTable ? (
        <DataTable
          columns={[{ key: chart.x, label: xLabel }, ...series.map((s) => ({ ...s, numeric: true }))]}
          rows={chart.rows}
          formatters={{
            ...(chart.x === "month" ? { month: (v) => formatMonth(String(v)) } : {}),
            ...Object.fromEntries(series.map((s) => [s.key, (v: unknown) => formatMoney(Number(v))])),
          }}
        />
      ) : chart.kind === "column" ? (
        <ColumnChart rows={chart.rows} x={chart.x} series={series} />
      ) : (
        <RankedBars rows={chart.rows} label={chart.x} value={chart.series[0]!} />
      )}
      <div className="mt-4">
        <SqlBlock sql={chart.sql} label={t("showSql")} />
      </div>
    </article>
  );
}
