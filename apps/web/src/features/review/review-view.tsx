"use client";

import { ArrowRight, Info, Loader2, MousePointerClick, Table2, Undo2 } from "lucide-react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useMemo, useState } from "react";

import { TransformStep, useTransformLabel } from "@/components/transform-detail";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ErrorState, ScoreRing, Skeleton } from "@/components/ui/misc";
import { ConfirmDialog } from "@/components/ui/sheet";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Tooltip } from "@/components/ui/tooltip";
import type { Schemas } from "@/lib/api/client";
import {
  useTableDiff,
  useTransformations,
  useUndoTransformation,
  useUndoUpload,
  useUpload,
} from "@/lib/api/hooks";
import { KNOWN_ROLES, RoleIcon } from "@/lib/roles";
import { cn, formatDateTime } from "@/lib/utils";
import { formatValue } from "@/lib/values";

type Diff = Schemas["TableDiff"];
type Row = Diff["rows"][number];
type Selection = { rowIndex: number; fieldKey: string | null };

const PAGE = 100;

export function ReviewView({ ws, uploadId }: { ws: number; uploadId: number }) {
  const t = useTranslations("review");
  const tc = useTranslations("common");
  const upload = useUpload(uploadId);
  const [tableIndex, setTableIndex] = useState(0);
  const table = upload.data?.tables[tableIndex];
  const [limit, setLimit] = useState(PAGE);
  const diff = useTableDiff(table?.id, limit);
  const transforms = useTransformations(table?.id);
  const undoUpload = useUndoUpload();
  const [confirmUndo, setConfirmUndo] = useState(false);
  const [kindFilter, setKindFilter] = useState<string | null>(null);
  const [onlyChanged, setOnlyChanged] = useState(false);
  const [selected, setSelected] = useState<Selection | null>(null);
  const label = useTransformLabel();
  const tTable = useTranslations("table");

  const rows = useMemo(() => {
    const all = diff.data?.rows ?? [];
    return all.filter((row) => {
      if (!onlyChanged && !kindFilter) return true;
      const kinds = rowKinds(row);
      if (kindFilter) return kinds.includes(kindFilter);
      return kinds.length > 0 || row.skip_reason !== null;
    });
  }, [diff.data, onlyChanged, kindFilter]);

  if (upload.isError) {
    return <ErrorState title={tc("notFound")} />;
  }
  if (upload.isPending || !upload.data) {
    return <Skeleton className="h-96 rounded-2xl" />;
  }
  const detail = upload.data;
  const undone = detail.status === "undone";
  const selectedRow = selected ? diff.data?.rows.find((r) => r.row_index === selected.rowIndex) : undefined;

  return (
    <div className="mx-auto max-w-[1400px]">
      <header className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div className="min-w-0">
          <p className="text-sm text-ink-faint">{t("title")}</p>
          <h1 className="display mt-1 truncate text-2xl font-semibold sm:text-3xl">{detail.filename}</h1>
          <p className="mt-1 text-sm text-ink-muted">
            {t("uploadedAt", { date: formatDateTime(detail.created_at) })}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {table?.dataset_id ? (
            <Button asChild variant="secondary">
              <Link href={`/w/${ws}/veri/${table.dataset_id}`}>
                <Table2 />
                {t("openTable")}
              </Link>
            </Button>
          ) : null}
          {!undone && detail.status === "done" ? (
            <Button variant="danger" onClick={() => setConfirmUndo(true)}>
              <Undo2 />
              {t("undoUpload")}
            </Button>
          ) : null}
        </div>
      </header>

      {undone ? (
        <div className="mb-6 flex items-center gap-3 rounded-xl border border-rule bg-paper-sunken px-4 py-3 text-sm text-ink-muted">
          <Info className="size-4 shrink-0" />
          {t("undoneUploadBanner")}
        </div>
      ) : null}

      {detail.tables.length > 1 ? (
        <Tabs value={String(tableIndex)} onValueChange={(v) => { setTableIndex(Number(v)); setSelected(null); }} className="mb-6">
          <TabsList>
            {detail.tables.map((tb, i) => (
              <TabsTrigger key={tb.id} value={String(i)}>
                {tb.sheet ?? `#${i + 1}`}
              </TabsTrigger>
            ))}
          </TabsList>
        </Tabs>
      ) : null}

      {/* How each column was recognised */}
      {table ? (
        <section className="mb-6">
          <h2 className="mb-3 text-sm font-medium text-ink-muted">{t("columns")}</h2>
          <div className="flex flex-wrap gap-2">
            {table.columns.map((col) => (
              <ColumnMapping key={col.col_index} column={col} />
            ))}
          </div>
        </section>
      ) : null}

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_340px]">
        <section className="min-w-0">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
            <label className="inline-flex cursor-pointer items-center gap-2 text-sm text-ink-muted">
              <input
                type="checkbox"
                checked={onlyChanged}
                onChange={(e) => setOnlyChanged(e.target.checked)}
                className="size-4 accent-[var(--accent)]"
              />
              {t("onlyChanged")}
            </label>
            {diff.data ? (
              <span className="text-xs text-ink-faint tnum">
                {t("rows", { shown: diff.data.rows.length, total: diff.data.total_rows })}
              </span>
            ) : null}
          </div>
          {diff.data ? (
            <DiffTable diff={diff.data} rows={rows} selected={selected} onSelect={setSelected} />
          ) : (
            <Skeleton className="h-96 rounded-2xl" />
          )}
          {diff.data && diff.data.rows.length < diff.data.total_rows ? (
            <div className="mt-4 flex justify-center">
              <Button variant="secondary" onClick={() => setLimit((l) => l + PAGE)} disabled={diff.isFetching}>
                {diff.isFetching ? <Loader2 className="animate-spin" /> : null}
                {tc("more")}
              </Button>
            </div>
          ) : null}
        </section>

        <aside className="flex flex-col gap-4 xl:sticky xl:top-6 xl:self-start">
          {selectedRow ? (
            <SelectedCell row={selectedRow} fieldKey={selected!.fieldKey} diff={diff.data!} />
          ) : (
            <div className="flex gap-3 rounded-2xl border border-dashed border-rule-strong px-4 py-4 text-sm text-ink-muted">
              <MousePointerClick className="mt-0.5 size-4 shrink-0 text-accent" />
              {tTable("cellHint")}
            </div>
          )}
          <div className="rounded-2xl border border-rule bg-paper-raised p-4">
            <h2 className="mb-3 font-semibold">{t("changesTitle")}</h2>
            {transforms.data && transforms.data.summary.length === 0 ? (
              <p className="text-sm text-ink-muted">{t("noChanges")}</p>
            ) : null}
            <div className="flex flex-col gap-1">
              {transforms.data?.summary.map((s) => (
                <button
                  key={s.kind}
                  type="button"
                  onClick={() => setKindFilter((k) => (k === s.kind ? null : s.kind))}
                  aria-pressed={kindFilter === s.kind}
                  className={cn(
                    "flex items-center justify-between rounded-lg px-3 py-2 text-left text-sm transition-colors hover:bg-paper-sunken",
                    kindFilter === s.kind && "bg-accent-soft text-accent hover:bg-accent-soft",
                  )}
                >
                  <span>{label(s.kind)}</span>
                  <span className="text-xs text-ink-faint tnum">
                    {s.undone > 0 ? `${s.count - s.undone} / ${s.count}` : s.count}
                  </span>
                </button>
              ))}
            </div>
          </div>
        </aside>
      </div>

      <ConfirmDialog
        open={confirmUndo}
        onOpenChange={setConfirmUndo}
        title={t("undoUpload")}
        body={t("undoUploadConfirm")}
        confirmLabel={t("undoUpload")}
        busy={undoUpload.isPending}
        onConfirm={() => undoUpload.mutate(uploadId, { onSuccess: () => setConfirmUndo(false) })}
      />
    </div>
  );
}

function rowKinds(row: Row): string[] {
  const record = row.record;
  if (!record) return [];
  const kinds = record.row_transforms.map((t) => t.kind);
  for (const list of Object.values(record.transforms)) {
    for (const tr of list) if (tr.kind !== "text_trimmed") kinds.push(tr.kind);
  }
  return kinds;
}

function ColumnMapping({ column }: { column: Schemas["SourceColumnOut"] }) {
  const tr = useTranslations("roles");
  const tReasons = useTranslations("reasons");
  const reasons = (column.reasons ?? []).map((r) => {
    const code = String(r.code);
    const params = (r.params ?? {}) as Record<string, unknown>;
    const values: Record<string, string> = {};
    for (const [k, v] of Object.entries(params)) {
      values[k] = typeof v === "number" && k === "ratio" ? String(Math.round(v * 100)) : String(v);
    }
    try {
      return tReasons(code as "header_match", values as { keyword: string });
    } catch {
      return code;
    }
  });
  const role = KNOWN_ROLES.has(column.role) ? tr(column.role as "party") : column.role;
  return (
    <Tooltip content={reasons.length ? <ul>{reasons.map((r) => <li key={r}>{r}</li>)}</ul> : null}>
      <div className="flex items-center gap-2 rounded-xl border border-rule bg-paper-raised py-1.5 pr-3 pl-1.5 text-sm">
        <ScoreRing value={column.confidence} size={30} />
        <span className="max-w-[9rem] truncate font-mono text-xs text-ink-muted">{column.header}</span>
        <ArrowRight className="size-3.5 text-ink-faint" />
        <span className="inline-flex items-center gap-1 font-medium">
          <RoleIcon role={column.role} className="size-3.5 text-accent" />
          {role}
        </span>
        {column.engine === "llm" ? <Badge tone="accent">AI</Badge> : null}
      </div>
    </Tooltip>
  );
}

function DiffTable({
  diff,
  rows,
  selected,
  onSelect,
}: {
  diff: Diff;
  rows: Row[];
  selected: Selection | null;
  onSelect: (s: Selection) => void;
}) {
  const t = useTranslations("review");
  const tSkip = useTranslations("skip");
  const rawCols = diff.columns;

  return (
    <div className="overflow-x-auto rounded-2xl border border-rule bg-paper-raised">
      <table className="w-full text-sm">
        <thead className="sticky top-0 z-10 bg-paper-raised">
          <tr className="border-b border-rule text-xs text-ink-faint">
            <th className="w-12 px-3 py-2 text-right font-normal">#</th>
            <th colSpan={rawCols.length} className="border-r border-rule px-3 py-2 text-left font-medium tracking-wide uppercase">
              {t("original")}
            </th>
            <th colSpan={Math.max(diff.fields.length, 1)} className="px-3 py-2 text-left font-medium tracking-wide text-accent uppercase">
              {t("clean")}
            </th>
          </tr>
          <tr className="border-b border-rule text-left">
            <th />
            {rawCols.map((c, i) => (
              <th
                key={c.col_index}
                className={cn("px-3 py-2 font-mono text-xs font-normal whitespace-nowrap text-ink-muted", i === rawCols.length - 1 && "border-r border-rule")}
              >
                {c.header}
              </th>
            ))}
            {diff.fields.map((f) => (
              <th key={f.key} className="px-3 py-2 text-xs font-semibold whitespace-nowrap">
                {f.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const record = row.record;
            const duplicate = record?.status === "duplicate";
            const rowSelected = selected?.rowIndex === row.row_index;
            return (
              <tr
                key={row.row_index}
                className={cn(
                  "border-b border-rule/60 last:border-0",
                  (row.skip_reason || duplicate) && "bg-paper-sunken/60 text-ink-faint",
                  row.row_index === diff.header_row && "bg-accent-soft/40",
                  rowSelected && "bg-accent-soft/50",
                )}
              >
                <td className="px-3 py-2 text-right text-xs text-ink-faint tnum">{row.row_index}</td>
                {rawCols.map((c, i) => (
                  <td
                    key={c.col_index}
                    className={cn(
                      "max-w-[14rem] truncate px-3 py-2 font-mono text-[13px] whitespace-nowrap text-ink-muted",
                      i === rawCols.length - 1 && "border-r border-rule",
                    )}
                  >
                    {row.raw[c.col_index] ?? ""}
                  </td>
                ))}
                {row.row_index === diff.header_row ? (
                  <td colSpan={diff.fields.length} className="px-3 py-2">
                    <Badge tone="accent">{tSkip("header")}</Badge>
                  </td>
                ) : row.skip_reason ? (
                  <td colSpan={diff.fields.length} className="px-3 py-2">
                    <Badge tone="outline">
                      {t("skipped")}: {tSkip(row.skip_reason as "title")}
                    </Badge>
                  </td>
                ) : record ? (
                  diff.fields.map((f, i) => {
                    const changes = (record.transforms[f.key] ?? []).filter((x) => x.kind !== "text_trimmed");
                    const active = changes.filter((x) => !x.undone);
                    const failed = active.some((x) => x.kind === "parse_failed");
                    const isSel = rowSelected && selected?.fieldKey === f.key;
                    return (
                      <td key={f.key} className="relative px-1 py-1">
                        <button
                          type="button"
                          onClick={() => onSelect({ rowIndex: row.row_index, fieldKey: f.key })}
                          className={cn(
                            "w-full rounded-md px-2 py-1 text-left whitespace-nowrap hover:bg-paper-sunken",
                            isSel && "ring-2 ring-accent",
                            duplicate && "line-through",
                            failed && "bg-warn-soft text-warn",
                          )}
                        >
                          <span className={cn(active.length > 0 && !failed && "corrected", !duplicate && "text-ink")}>
                            {formatValue(record.values[f.key], f)}
                          </span>
                        </button>
                        {duplicate && i === 0 ? (
                          <button
                            type="button"
                            onClick={() => onSelect({ rowIndex: row.row_index, fieldKey: null })}
                            className="absolute -top-1.5 left-2 rounded-full bg-warn-soft px-2 text-[10px] font-medium text-warn no-underline"
                          >
                            {t("duplicateRow")}
                          </button>
                        ) : null}
                      </td>
                    );
                  })
                ) : (
                  <td colSpan={diff.fields.length} />
                )}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function SelectedCell({ row, fieldKey, diff }: { row: Row; fieldKey: string | null; diff: Diff }) {
  const tc = useTranslations("common");
  const tp = useTranslations("provenance");
  const undo = useUndoTransformation();
  const record = row.record;
  const field = diff.fields.find((f) => f.key === fieldKey);
  const steps = !record
    ? []
    : fieldKey === null
      ? record.row_transforms
      : (record.transforms[fieldKey] ?? []);

  return (
    <div className="rounded-2xl border border-rule bg-paper-raised p-4 animate-fade-up">
      <p className="text-xs text-ink-faint">
        {tc("row", { row: row.row_index })}
        {field ? ` · ${field.label}` : ""}
      </p>
      {field && record ? (
        <p className="display mt-1 text-xl font-semibold">{formatValue(record.values[field.key], field)}</p>
      ) : null}
      <div className="mt-3 flex flex-col gap-2">
        {steps.length === 0 ? (
          <p className="text-sm text-ink-muted">{tp("noSteps")}</p>
        ) : (
          steps.map((step) => (
            <TransformStep
              key={step.id}
              transform={step}
              undoing={undo.isPending && undo.variables === step.id}
              onUndo={() => undo.mutate(step.id)}
            />
          ))
        )}
      </div>
    </div>
  );
}
