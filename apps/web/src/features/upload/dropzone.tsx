"use client";

import { FileUp } from "lucide-react";
import { useTranslations } from "next-intl";
import { useId, useRef, useState } from "react";

import { cn } from "@/lib/utils";

const ACCEPT = ".xlsx,.xlsm,.csv,.tsv,.txt";

export function Dropzone({ onFiles, compact }: { onFiles: (files: File[]) => void; compact?: boolean }) {
  const t = useTranslations("upload");
  const inputId = useId();
  const input = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  const depth = useRef(0);

  return (
    <div
      onDragEnter={(e) => {
        e.preventDefault();
        depth.current += 1;
        setOver(true);
      }}
      onDragOver={(e) => e.preventDefault()}
      onDragLeave={() => {
        depth.current -= 1;
        if (depth.current <= 0) setOver(false);
      }}
      onDrop={(e) => {
        e.preventDefault();
        depth.current = 0;
        setOver(false);
        const files = Array.from(e.dataTransfer.files);
        if (files.length) onFiles(files);
      }}
      className={cn(
        "ruled relative rounded-3xl border-2 border-dashed px-6 pl-16 text-center transition-all sm:pl-20",
        compact ? "py-8" : "py-16 sm:py-24",
        over ? "scale-[1.01] border-accent bg-accent-soft" : "border-rule-strong",
      )}
    >
      <div
        className={cn(
          "mx-auto grid size-14 place-items-center rounded-2xl bg-paper-raised text-accent shadow-card transition-transform",
          over && "-translate-y-1 rotate-[-4deg]",
          compact && "size-11",
        )}
      >
        <FileUp className={compact ? "size-5" : "size-6"} />
      </div>
      <p className={cn("display mt-5 font-semibold", compact ? "text-lg" : "text-2xl")}>
        {over ? t("dropActive") : t("drop")}
      </p>
      <p className="mt-2 text-sm text-ink-muted">
        {t("or")}{" "}
        <label htmlFor={inputId} className="cursor-pointer font-medium text-accent underline-offset-4 hover:underline">
          {t("choose")}
        </label>
      </p>
      <p className="mt-4 text-xs text-ink-faint">{t("formats")}</p>
      <input
        id={inputId}
        ref={input}
        type="file"
        multiple
        accept={ACCEPT}
        className="sr-only"
        onChange={(e) => {
          const files = Array.from(e.target.files ?? []);
          if (files.length) onFiles(files);
          if (input.current) input.current.value = "";
        }}
      />
    </div>
  );
}
