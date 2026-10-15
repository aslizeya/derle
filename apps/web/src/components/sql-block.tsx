"use client";

import { Check, ChevronRight, Copy } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { cn } from "@/lib/utils";

/** Collapsible, copyable SQL: the "show your work" panel used by dashboards and answers. */
export function SqlBlock({
  sql,
  label,
  note,
  defaultOpen = false,
}: {
  sql: string;
  label: string;
  note?: string;
  defaultOpen?: boolean;
}) {
  const t = useTranslations("ask");
  const [copied, setCopied] = useState(false);
  return (
    <details className="group rounded-xl border border-rule bg-paper" open={defaultOpen}>
      <summary className="flex cursor-pointer list-none items-center gap-2 px-3 py-2 text-xs font-medium text-ink-muted select-none hover:text-ink [&::-webkit-details-marker]:hidden">
        <ChevronRight className="size-3.5 transition-transform group-open:rotate-90" />
        {label}
        {note ? <span className="ml-auto font-normal text-ink-faint">{note}</span> : null}
      </summary>
      <div className="relative border-t border-rule">
        <pre className="overflow-x-auto px-4 py-3 font-mono text-[12.5px] leading-relaxed text-ink">{sql}</pre>
        <button
          type="button"
          onClick={() => {
            void navigator.clipboard?.writeText(sql);
            setCopied(true);
            window.setTimeout(() => setCopied(false), 1500);
          }}
          className={cn(
            "absolute top-2 right-2 inline-flex items-center gap-1 rounded-md border border-rule bg-paper-raised px-2 py-1 text-[11px] text-ink-muted hover:text-ink",
            copied && "text-ok",
          )}
        >
          {copied ? <Check className="size-3" /> : <Copy className="size-3" />}
          {copied ? t("copied") : t("copy")}
        </button>
      </div>
    </details>
  );
}
