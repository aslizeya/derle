"use client";

import {
  type ColumnDef,
  flexRender,
  getCoreRowModel,
  type SortingState,
  useReactTable,
} from "@tanstack/react-table";
import { ArrowDown, ArrowUp, ArrowUpDown, ChevronLeft, ChevronRight, Eye, EyeOff, Search } from "lucide-react";
import { useTranslations } from "next-intl";
import { useDeferredValue, useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { ErrorState, Input, Skeleton } from "@/components/ui/misc";
import { Tooltip } from "@/components/ui/tooltip";
import type { Schemas } from "@/lib/api/client";
import { useDataset, useRecords } from "@/lib/api/hooks";
import { RoleIcon } from "@/lib/roles";
import { cn } from "@/lib/utils";
import { formatValue } from "@/lib/values";

import { type CellRef, ProvenanceSheet } from "./provenance-sheet";
import { TableHeader } from "./table-header";

type Field = Schemas["FieldOut"];
type Row = Record<string, unknown>;
type Mark = Schemas["CellMark"];

const PAGE_SIZE = 50;

export function TableView({
  ws,
  datasetId,
  initialSort,
}: {
  ws: number;
  datasetId: number;
  initialSort?: { id: string; desc: boolean };
}) {
  const t = useTranslations("table");
  const tc = useTranslations("common");
  const dataset = useDataset(datasetId);
  const [sorting, setSorting] = useState<SortingState>(initialSort ? [initialSort] : []);
  const [search, setSearch] = useState("");
  const query = useDeferredValue(search.trim());
  const [page, setPage] = useState(0);
  const [maskPersonal, setMaskPersonal] = useState(true);
  const [cell, setCell] = useState<CellRef | null>(null);

  const sort = sorting[0];
  const records = useRecords(datasetId, {
    limit: PAGE_SIZE,
    offset: page * PAGE_SIZE,
    sort: sort?.id,
    desc: sort?.desc,
    q: query,
  });

  const fields = useMemo(() => dataset.data?.fields ?? [], [dataset.data]);
  const hasParty = fields.some((f) => f.role === "party");
  const marks = records.data?.marks ?? {};

  const columns = useMemo<ColumnDef<Row>[]>(() => {
    const cols: ColumnDef<Row>[] = fields.map((field) => ({
      id: field.column,
      accessorKey: field.column,
      header: field.label,
      meta: { field },
    }));
    if (hasParty) {
      cols.splice(1, 0, { id: "party_canonical", accessorKey: "party_canonical", header: t("linkedCustomer") });
    }
    return cols;
  }, [fields, hasParty, t]);

  // TanStack Table v8 is not React Compiler compatible; this component opts out of memoization.
  // eslint-disable-next-line react-hooks/incompatible-library
  const table = useReactTable({
    data: (records.data?.rows ?? []) as Row[],
    columns,
    state: { sorting },
    manualSorting: true,
    enableSortingRemoval: true,
    onSortingChange: (updater) => {
      setSorting(updater);
      setPage(0);
    },
    getCoreRowModel: getCoreRowModel(),
  });

  if (dataset.isError) return <ErrorState title={tc("notFound")} />;

  const total = records.data?.total ?? 0;
  const from = total === 0 ? 0 : page * PAGE_SIZE + 1;
  const to = Math.min(total, (page + 1) * PAGE_SIZE);

  return (
    <div className="mx-auto max-w-[1400px]">
      <TableHeader ws={ws} datasetId={datasetId} name={dataset.data?.name} maskPersonal={maskPersonal} />

      <div className="mb-4 flex flex-wrap items-center gap-3">
        <div className="relative w-full max-w-sm">
          <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-ink-faint" />
          <Input
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setPage(0);
            }}
            placeholder={t("search")}
            className="pl-9"
            aria-label={t("search")}
          />
        </div>
        <Button variant="ghost" size="sm" onClick={() => setMaskPersonal((m) => !m)}>
          {maskPersonal ? <Eye /> : <EyeOff />}
          {maskPersonal ? tc("showPii") : tc("hidePii")}
        </Button>
        <span className="ml-auto text-sm text-ink-faint tnum">{t("page", { from, to, total })}</span>
      </div>

      <div className="overflow-x-auto rounded-2xl border border-rule bg-paper-raised">
        <table className="w-full text-sm">
          <thead className="border-b border-rule bg-paper-sunken/40">
            {table.getHeaderGroups().map((group) => (
              <tr key={group.id}>
                {group.headers.map((header) => {
                  const field = (header.column.columnDef.meta as { field?: Field } | undefined)?.field;
                  const sorted = header.column.getIsSorted();
                  const numeric = field?.dtype === "number";
                  return (
                    <th key={header.id} className={cn("px-2 py-1.5 font-medium", numeric ? "text-right" : "text-left")}>
                      <button
                        type="button"
                        onClick={header.column.getToggleSortingHandler()}
                        className={cn(
                          "inline-flex items-center gap-1.5 rounded-md px-2 py-1 whitespace-nowrap hover:bg-paper-sunken",
                          numeric && "flex-row-reverse",
                        )}
                        title={sorted === "asc" ? t("sortDesc") : t("sortAsc")}
                      >
                        {field ? <RoleIcon role={field.role} className="size-3.5 text-ink-faint" /> : null}
                        {flexRender(header.column.columnDef.header, header.getContext())}
                        {sorted === "asc" ? (
                          <ArrowUp className="size-3.5 text-accent" />
                        ) : sorted === "desc" ? (
                          <ArrowDown className="size-3.5 text-accent" />
                        ) : (
                          <ArrowUpDown className="size-3.5 text-ink-faint/60" />
                        )}
                      </button>
                    </th>
                  );
                })}
              </tr>
            ))}
          </thead>
          <tbody className={cn(records.isFetching && "opacity-70 transition-opacity")}>
            {records.isPending
              ? Array.from({ length: 8 }, (_, i) => (
                  <tr key={i} className="border-b border-rule/60">
                    <td colSpan={Math.max(columns.length, 1)} className="px-4 py-2.5">
                      <Skeleton className="h-5" />
                    </td>
                  </tr>
                ))
              : table.getRowModel().rows.map((row) => {
                  const recordId = Number(row.original.record_id);
                  const rowMarks = marks[String(recordId)] ?? {};
                  return (
                    <tr key={row.id} className="border-b border-rule/60 last:border-0 hover:bg-paper-sunken/40">
                      {row.getVisibleCells().map((c) => {
                        const field = (c.column.columnDef.meta as { field?: Field } | undefined)?.field;
                        const value = c.getValue();
                        if (!field) {
                          return (
                            <td key={c.id} className="px-4 py-2 whitespace-nowrap text-ink-muted">
                              {value ? String(value) : "—"}
                            </td>
                          );
                        }
                        return (
                          <td key={c.id} className={cn("p-1", field.dtype === "number" && "text-right")}>
                            <DataCell
                              value={value}
                              field={field}
                              mark={rowMarks[field.column]}
                              mask={maskPersonal}
                              onOpen={() => setCell({ recordId, field })}
                            />
                          </td>
                        );
                      })}
                    </tr>
                  );
                })}
          </tbody>
        </table>
        {records.data && records.data.rows.length === 0 ? (
          <p className="px-4 py-10 text-center text-sm text-ink-muted">{t("noResults")}</p>
        ) : null}
      </div>

      <div className="mt-4 flex items-center justify-end gap-2">
        <Button variant="secondary" size="sm" onClick={() => setPage((p) => p - 1)} disabled={page === 0}>
          <ChevronLeft />
          {t("prev")}
        </Button>
        <Button variant="secondary" size="sm" onClick={() => setPage((p) => p + 1)} disabled={to >= total}>
          {t("next")}
          <ChevronRight />
        </Button>
      </div>

      <ProvenanceSheet ws={ws} cell={cell} onClose={() => setCell(null)} maskPersonal={maskPersonal} />
    </div>
  );
}

function DataCell({
  value,
  field,
  mark,
  mask,
  onOpen,
}: {
  value: unknown;
  field: Field;
  mark?: Mark;
  mask: boolean;
  onOpen: () => void;
}) {
  const t = useTranslations("table.marks");
  // Undone or unparseable values have no typed value; show the original text instead.
  const showRaw = mark && (mark.state === "original" || mark.state === "failed") && (value === null || value === undefined);
  const text = showRaw ? (mark.raw ?? "—") : formatValue(value, field, mask);
  const content = (
    <button
      type="button"
      onClick={onOpen}
      className={cn(
        "w-full rounded-md px-3 py-1.5 whitespace-nowrap hover:bg-accent-soft/60",
        field.dtype === "number" ? "text-right" : "text-left",
        mark?.state === "failed" && "bg-warn-soft text-warn",
        mark?.state === "original" && "font-mono text-[13px] text-ink-muted italic",
      )}
    >
      <span className={cn(mark?.state === "changed" && "corrected")}>{text}</span>
    </button>
  );
  return mark ? <Tooltip content={t(mark.state)}>{content}</Tooltip> : content;
}
