"use client";

import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { cn } from "@/lib/utils";

type Fix = "date" | "amount" | "name" | "phone" | null;
type Cell = { before: string; after: string; fix: Fix };

const HEADER: Cell[] = [
  { before: "gün", after: "Tarih", fix: null },
  { before: "KİM", after: "Müşteri", fix: null },
  { before: "tutar(tl)", after: "Tutar", fix: null },
  { before: "tel", after: "Telefon", fix: null },
];

const ROWS: Cell[][] = [
  [
    { before: "3 Mart", after: "3 Mar 2026", fix: "date" },
    { before: "ahmet bey", after: "Ahmet Yılmaz", fix: "name" },
    { before: "1.250 TL", after: "₺1.250,00", fix: "amount" },
    { before: "0532 123 45 67", after: "0532 123 45 67", fix: null },
  ],
  [
    { before: "04.03.26", after: "4 Mar 2026", fix: "date" },
    { before: "A. YILMAZ", after: "Ahmet Yılmaz", fix: "name" },
    { before: "850", after: "₺850,00", fix: "amount" },
    { before: "+90 532 1234567", after: "0532 123 45 67", fix: "phone" },
  ],
  [
    { before: "5/3", after: "5 Mar 2026", fix: "date" },
    { before: "Yılmaz, Mehmet", after: "Mehmet Yılmaz", fix: "name" },
    { before: "2 bin", after: "₺2.000,00", fix: "amount" },
    { before: "", after: "—", fix: null },
  ],
  [
    { before: "Pazartesi 9 Mart", after: "9 Mar 2026", fix: "date" },
    { before: "AYŞE HANIM", after: "Ayşe Kaya", fix: "name" },
    { before: "75,50 TL", after: "₺75,50", fix: "amount" },
    { before: "05329876543", after: "0532 987 65 43", fix: "phone" },
  ],
];
const DUPLICATE = ROWS[3]!;

// One step per header cell, one per body cell, one for the duplicate row, then a pause.
const STEPS = HEADER.length + ROWS.length * 4 + 1;
const STEP_MS = 420;
const HOLD_STEPS = 9;

export function BeforeAfter() {
  const t = useTranslations("landing.beforeAfter");
  const reduce = useReducedMotion();
  const [step, setStep] = useState(0);

  useEffect(() => {
    if (reduce) return;
    const id = window.setInterval(() => setStep((s) => (s + 1) % (STEPS + HOLD_STEPS)), STEP_MS);
    return () => window.clearInterval(id);
  }, [reduce]);

  const done = (index: number) => reduce || step > index;
  const finished = done(STEPS - 1);

  return (
    <figure className="relative">
      <div className="overflow-hidden rounded-2xl border border-rule bg-paper-raised shadow-card">
        <div className="flex items-center justify-between border-b border-rule px-4 py-2.5 text-xs text-ink-faint">
          <span className="font-mono">mart_2026.xlsx</span>
          <span
            className={cn(
              "rounded-full px-2 py-0.5 font-medium transition-colors",
              finished ? "bg-ok-soft text-ok" : "bg-paper-sunken text-ink-muted",
            )}
          >
            {finished ? t("after") : t("before")}
          </span>
        </div>
        <div className={cn("overflow-x-auto transition-colors duration-700", !finished && "ruled")}>
          <table className="w-full min-w-[520px] text-sm">
            <thead>
              <tr className="border-b border-rule text-left">
                {HEADER.map((cell, i) => (
                  <th key={i} className="h-10 px-4 font-medium text-ink-muted">
                    <Swap cell={cell} on={done(i)} className={done(i) ? "text-ink" : "font-mono font-normal italic"} />
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {ROWS.map((row, r) => (
                <tr key={r} className="border-b border-rule/70">
                  {row.map((cell, c) => {
                    const index = HEADER.length + r * 4 + c;
                    return (
                      <td key={c} className="relative h-11 px-4 whitespace-nowrap">
                        <Swap cell={cell} on={done(index)} />
                        <FixChip fix={cell.fix} show={!reduce && step === index + 1} />
                      </td>
                    );
                  })}
                </tr>
              ))}
              <tr className={cn("transition-opacity duration-500", done(STEPS - 1) && "opacity-45")}>
                {DUPLICATE.map((cell, c) => (
                  <td key={c} className="relative h-11 px-4 whitespace-nowrap">
                    <span className={cn("font-mono text-[13px] text-ink-muted", done(STEPS - 1) && "line-through")}>
                      {cell.before || " "}
                    </span>
                    {c === 0 ? (
                      <span
                        className={cn(
                          "absolute -top-2 left-3 rounded-full bg-warn-soft px-2 py-0.5 text-[11px] font-medium text-warn transition-all",
                          done(STEPS - 1) ? "opacity-100" : "translate-y-1 opacity-0",
                        )}
                      >
                        {t("fixes.duplicate")}
                      </span>
                    ) : null}
                  </td>
                ))}
              </tr>
            </tbody>
          </table>
        </div>
      </div>
      <figcaption className="mt-3 text-center text-xs text-ink-faint">{t("caption")}</figcaption>
    </figure>
  );
}

function Swap({ cell, on, className }: { cell: Cell; on: boolean; className?: string }) {
  return (
    <span className="relative inline-block">
      <AnimatePresence mode="popLayout" initial={false}>
        <motion.span
          key={on ? "after" : "before"}
          initial={{ y: 10, opacity: 0, filter: "blur(2px)" }}
          animate={{ y: 0, opacity: 1, filter: "blur(0px)" }}
          exit={{ y: -10, opacity: 0, filter: "blur(2px)" }}
          transition={{ duration: 0.28, ease: [0.2, 0.7, 0.2, 1] }}
          className={cn(
            "inline-block",
            on
              ? cn(cell.fix && "corrected", "text-ink")
              : "font-mono text-[13px] text-ink-muted",
            className,
          )}
        >
          {(on ? cell.after : cell.before) || " "}
        </motion.span>
      </AnimatePresence>
    </span>
  );
}

function FixChip({ fix, show }: { fix: Fix; show: boolean }) {
  const t = useTranslations("landing.beforeAfter.fixes");
  return (
    <AnimatePresence>
      {fix && show ? (
        <motion.span
          initial={{ opacity: 0, y: 4, scale: 0.9 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={{ opacity: 0, y: -4 }}
          transition={{ duration: 0.2 }}
          className="pointer-events-none absolute -top-2 left-3 rounded-full bg-accent px-2 py-0.5 text-[11px] font-medium text-accent-ink shadow-sm"
        >
          {t(fix)}
        </motion.span>
      ) : null}
    </AnimatePresence>
  );
}
