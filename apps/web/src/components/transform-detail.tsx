"use client";

import { ArrowRight, Loader2, Undo2 } from "lucide-react";
import { useTranslations } from "next-intl";

import { Badge } from "@/components/ui/badge";
import type { Schemas } from "@/lib/api/client";
import { KNOWN_TRANSFORMS } from "@/lib/roles";
import { cn } from "@/lib/utils";

type Transform = Pick<Schemas["TransformOut"], "kind" | "before" | "after" | "confidence" | "detail" | "undone"> & {
  id?: number;
};

export function useTransformLabel() {
  const t = useTranslations("transforms");
  return (kind: string) => (KNOWN_TRANSFORMS.has(kind) ? t(kind as "date_parsed") : kind);
}

/** Human-readable notes from a transformation's detail payload. */
export function useTransformNotes() {
  const t = useTranslations("transforms.details");
  return (detail: Record<string, unknown>): string[] => {
    const notes: string[] = [];
    if (detail.year_inferred) notes.push(t("yearInferred", { year: String(detail.year_inferred) }));
    if (detail.ambiguous_order) notes.push(t("ambiguousOrder"));
    if (detail.ambiguous) notes.push(t("ambiguousNumber"));
    if (Array.isArray(detail.removed)) notes.push(t("removed", { words: detail.removed.join(", ") }));
    if (detail.note) notes.push(t("note", { note: String(detail.note) }));
    if (detail.reordered) notes.push(t("reordered"));
    if (detail.currency) notes.push(t("currency", { code: String(detail.currency) }));
    if ("duplicate_of" in detail) notes.push(t("duplicateOf"));
    return notes;
  };
}

export function TransformStep({
  transform,
  onUndo,
  undoing,
  showUndo = true,
}: {
  transform: Transform;
  onUndo?: () => void;
  undoing?: boolean;
  showUndo?: boolean;
}) {
  const t = useTranslations("common");
  const label = useTransformLabel();
  const notes = useTransformNotes()(transform.detail);
  const failed = transform.kind === "parse_failed";

  return (
    <div className={cn("rounded-xl border border-rule bg-paper p-3", transform.undone && "opacity-60")}>
      <div className="flex items-center justify-between gap-2">
        <Badge tone={failed ? "warn" : transform.undone ? "neutral" : "accent"}>{label(transform.kind)}</Badge>
        {transform.undone ? (
          <span className="text-xs text-ink-faint">{t("undone")}</span>
        ) : showUndo && onUndo && !failed ? (
          <button
            type="button"
            onClick={onUndo}
            disabled={undoing}
            className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium text-ink-muted hover:bg-paper-sunken hover:text-ink disabled:opacity-50"
          >
            {undoing ? <Loader2 className="size-3 animate-spin" /> : <Undo2 className="size-3" />}
            {t("undo")}
          </button>
        ) : null}
      </div>
      {transform.before !== null || transform.after !== null ? (
        <p className="mt-2 flex flex-wrap items-center gap-2 text-sm">
          <span className="font-mono text-[13px] text-ink-muted">{transform.before ?? "—"}</span>
          {transform.after !== null ? (
            <>
              <ArrowRight className="size-3.5 text-ink-faint" />
              <span className={cn("font-medium", !transform.undone && "corrected")}>{transform.after}</span>
            </>
          ) : null}
        </p>
      ) : null}
      {notes.length || transform.confidence < 1 ? (
        <ul className="mt-2 space-y-0.5 text-xs text-ink-faint">
          {notes.map((n) => (
            <li key={n}>{n}</li>
          ))}
          {transform.confidence < 1 && !failed ? (
            <li>{t("confidence", { value: Math.round(transform.confidence * 100) })}</li>
          ) : null}
        </ul>
      ) : null}
    </div>
  );
}
