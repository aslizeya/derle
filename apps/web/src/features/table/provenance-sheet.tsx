"use client";

import { ArrowUpRight, FileSpreadsheet } from "lucide-react";
import Link from "next/link";
import { useTranslations } from "next-intl";

import { TransformStep } from "@/components/transform-detail";
import { Skeleton } from "@/components/ui/misc";
import { Sheet } from "@/components/ui/sheet";
import type { Schemas } from "@/lib/api/client";
import { useProvenance } from "@/lib/api/hooks";
import { cn, formatDateTime } from "@/lib/utils";
import { formatValue } from "@/lib/values";

export type CellRef = { recordId: number; field: Schemas["FieldOut"] };

export function ProvenanceSheet({
  ws,
  cell,
  onClose,
  maskPersonal,
}: {
  ws: number;
  cell: CellRef | null;
  onClose: () => void;
  maskPersonal: boolean;
}) {
  const t = useTranslations("provenance");
  const tc = useTranslations("common");
  const prov = useProvenance(cell?.recordId, cell?.field.id);
  const data = prov.data;
  const source = data?.source as
    | {
        upload_id: number;
        filename: string;
        uploaded_at: string;
        sheet: string | null;
        row: number;
        header_row: number | null;
        columns: { index: number; header: string }[];
        raw_row: (string | null)[];
      }
    | undefined;
  const highlighted = new Set(source?.columns.map((c) => c.index));
  const steps = (data?.transforms ?? []) as Schemas["TransformOut"][];

  return (
    <Sheet
      open={cell !== null}
      onOpenChange={(open) => !open && onClose()}
      title={t("title")}
      description={cell?.field.label}
    >
      {!data || !source || !cell ? (
        <div className="flex flex-col gap-3">
          <Skeleton className="h-16" />
          <Skeleton className="h-24" />
          <Skeleton className="h-32" />
        </div>
      ) : (
        <div className="flex flex-col gap-6">
          <div className="grid grid-cols-2 gap-3">
            <div className="rounded-xl border border-rule bg-paper p-3">
              <p className="text-xs text-ink-faint">{t("value")}</p>
              <p className="mt-1 font-semibold break-words">
                {formatValue(data.value, cell.field, maskPersonal)}
              </p>
            </div>
            <div className="rounded-xl border border-dashed border-rule-strong p-3">
              <p className="text-xs text-ink-faint">{t("original")}</p>
              <p className="mt-1 font-mono text-[13px] break-words text-ink-muted">
                {maskPersonal && cell.field.pii ? "•••" : (data.original ?? "—")}
              </p>
            </div>
          </div>

          <section>
            <h3 className="mb-2 text-sm font-medium">{t("source")}</h3>
            <div className="flex gap-3 rounded-xl border border-rule bg-paper p-3 text-sm">
              <FileSpreadsheet className="mt-0.5 size-4 shrink-0 text-accent" />
              <div className="min-w-0">
                <p className="truncate font-medium">{source.filename}</p>
                <p className="text-xs text-ink-muted">
                  {source.sheet ? `${tc("sheet", { name: source.sheet })} · ` : ""}
                  {tc("row", { row: source.row })}
                </p>
                <p className="text-xs text-ink-faint">{formatDateTime(source.uploaded_at)}</p>
              </div>
            </div>
          </section>

          <section>
            <h3 className="mb-2 text-sm font-medium">{t("rawRow")}</h3>
            <div className="ruled overflow-x-auto rounded-xl border border-rule pl-12">
              <table className="text-[13px]">
                <tbody>
                  <tr>
                    {source.raw_row.map((value, i) => (
                      <td
                        key={i}
                        className={cn(
                          "border-r border-rule/60 px-3 py-2 font-mono whitespace-nowrap text-ink-muted last:border-0",
                          highlighted.has(i) && "bg-accent-soft font-medium text-accent",
                        )}
                      >
                        {maskPersonal && highlighted.has(i) && cell.field.pii ? "•••" : (value ?? "")}
                      </td>
                    ))}
                  </tr>
                </tbody>
              </table>
            </div>
          </section>

          <section>
            <h3 className="mb-2 text-sm font-medium">{t("steps")}</h3>
            {steps.length === 0 ? (
              <p className="text-sm text-ink-muted">{t("noSteps")}</p>
            ) : (
              <div className="flex flex-col gap-2">
                {steps.map((step, i) => (
                  <TransformStep key={i} transform={step} showUndo={false} />
                ))}
              </div>
            )}
          </section>

          <Link
            href={`/w/${ws}/yuklemeler/${source.upload_id}`}
            className="inline-flex items-center gap-1 text-sm font-medium text-accent hover:underline"
          >
            {t("seeInReview")}
            <ArrowUpRight className="size-4" />
          </Link>
        </div>
      )}
    </Sheet>
  );
}
