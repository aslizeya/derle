"use client";

import { Check, Eye, EyeOff, HelpCircle, Loader2, PartyPopper, Phone, Undo2, X } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState, ErrorState, Kbd, ScoreRing, Skeleton } from "@/components/ui/misc";
import type { Schemas } from "@/lib/api/client";
import { useDecideMatch, useMatches, useUndoMatch } from "@/lib/api/hooks";
import { cn, formatDate, formatMoney, maskPii } from "@/lib/utils";

type Card = Schemas["MatchCard"];
type Decision = "same" | "different" | "skip";

const KEYS: Record<string, Decision | "undo"> = { a: "same", f: "different", g: "skip", z: "undo" };
const EXIT = { same: { x: 0, scale: 0.92 }, different: { x: 0, y: 40 }, skip: { x: 80 } } as const;

export function MatchingView({ ws }: { ws: number }) {
  const t = useTranslations("matching");
  const tc = useTranslations("common");
  const matches = useMatches(ws);
  const decide = useDecideMatch();
  const undo = useUndoMatch(ws);
  const [showPii, setShowPii] = useState(false);
  const [lastDecision, setLastDecision] = useState<Decision>("skip");
  const [toast, setToast] = useState<string | null>(null);
  const card = matches.data?.cards[0];
  const busy = decide.isPending || undo.isPending;

  const act = useCallback(
    (action: Decision | "undo") => {
      if (busy) return;
      if (action === "undo") {
        undo.mutate(undefined, { onSuccess: () => setToast(t("undo")) });
        return;
      }
      if (!card) return;
      setLastDecision(action);
      decide.mutate(
        { id: card.id, decision: action },
        { onSuccess: () => setToast(t(`decided.${action}`)) },
      );
    },
    [busy, card, decide, undo, t],
  );

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      if (e.target instanceof HTMLElement && e.target.closest("input, textarea, select")) return;
      const action = KEYS[e.key.toLocaleLowerCase("tr")];
      if (action) {
        e.preventDefault();
        act(action);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [act]);

  useEffect(() => {
    if (!toast) return;
    const id = window.setTimeout(() => setToast(null), 1600);
    return () => window.clearTimeout(id);
  }, [toast]);

  if (matches.isError) {
    return <ErrorState title={tc("error")} body={tc("errorDetail")} onRetry={() => matches.refetch()} retryLabel={tc("retry")} />;
  }

  return (
    <div className="mx-auto max-w-5xl">
      <header className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="display text-3xl font-semibold sm:text-4xl">{t("title")}</h1>
          <p className="mt-2 max-w-2xl text-ink-muted">{t("lead")}</p>
        </div>
        <div className="flex items-center gap-2">
          {matches.data && matches.data.total > 0 ? (
            <Badge tone="warn" className="text-sm">
              {t("remaining", { count: matches.data.total })}
            </Badge>
          ) : null}
          <Button variant="ghost" size="sm" onClick={() => setShowPii((v) => !v)}>
            {showPii ? <EyeOff /> : <Eye />}
            {showPii ? tc("hidePii") : tc("showPii")}
          </Button>
        </div>
      </header>

      {matches.isPending ? (
        <Skeleton className="h-[520px] rounded-3xl" />
      ) : !card ? (
        <EmptyState icon={<PartyPopper />} title={t("doneTitle")} body={t("doneBody")}>
          <Button variant="secondary" onClick={() => act("undo")} disabled={busy}>
            <Undo2 />
            {t("undo")}
          </Button>
        </EmptyState>
      ) : (
        <AnimatePresence mode="wait" initial={false}>
          <motion.div
            key={card.id}
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0, x: 0, scale: 1 }}
            exit={{ opacity: 0, ...EXIT[lastDecision] }}
            transition={{ duration: 0.22, ease: [0.2, 0.7, 0.2, 1] }}
          >
            <MatchCardView card={card} showPii={showPii} />
          </motion.div>
        </AnimatePresence>
      )}

      {card ? (
        <div className="sticky bottom-20 z-20 mt-6 rounded-2xl border border-rule bg-paper-raised/95 p-3 shadow-card backdrop-blur md:bottom-6">
          <div className="flex flex-wrap gap-2 [&>button]:min-w-[9.5rem] [&>button]:flex-1">
            <Button variant="ok" size="lg" onClick={() => act("same")} disabled={busy}>
              {decide.isPending && lastDecision === "same" ? <Loader2 className="animate-spin" /> : <Check />}
              {t("same")}
              <Kbd className="ml-1 hidden border-paper/40 bg-transparent text-paper sm:inline-flex">A</Kbd>
            </Button>
            <Button variant="danger" size="lg" onClick={() => act("different")} disabled={busy}>
              <X />
              {t("different")}
              <Kbd className="ml-1 hidden sm:inline-flex">F</Kbd>
            </Button>
            <Button variant="secondary" size="lg" onClick={() => act("skip")} disabled={busy}>
              <HelpCircle />
              {t("skip")}
              <Kbd className="ml-1 hidden sm:inline-flex">G</Kbd>
            </Button>
            <Button variant="ghost" size="lg" onClick={() => act("undo")} disabled={busy}>
              <Undo2 />
              {t("undo")}
              <Kbd className="ml-1 hidden sm:inline-flex">Z</Kbd>
            </Button>
          </div>
        </div>
      ) : null}

      <div aria-live="polite" className="pointer-events-none fixed inset-x-0 top-6 z-50 flex justify-center">
        <AnimatePresence>
          {toast ? (
            <motion.div
              initial={{ opacity: 0, y: -10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
              className="rounded-full bg-ink px-4 py-2 text-sm text-paper shadow-card"
            >
              {toast}
            </motion.div>
          ) : null}
        </AnimatePresence>
      </div>
    </div>
  );
}

function MatchCardView({ card, showPii }: { card: Card; showPii: boolean }) {
  const t = useTranslations("matching");
  const codes = useTranslations("matching.evidenceCodes");

  return (
    <article className="overflow-hidden rounded-3xl border border-rule bg-paper-raised shadow-card">
      <div className="grid md:grid-cols-2 xl:grid-cols-[1fr_14rem_1fr]">
        <Side side={card.left} showPii={showPii} />
        <div className="order-first flex flex-row items-center gap-5 border-b border-rule bg-paper-sunken/50 px-5 py-4 md:col-span-2 xl:order-none xl:col-span-1 xl:flex-col xl:justify-center xl:border-x xl:border-b-0 xl:py-8">
          <div className="flex flex-col items-center">
            <ScoreRing value={card.score} size={68} />
            <p className="mt-1 text-xs text-ink-faint">{t("score")}</p>
          </div>
          <div className="w-full">
            <p className="mb-2 text-xs font-medium text-ink-muted">{t("evidence")}</p>
            <ul className="flex flex-col gap-1.5">
              {card.evidence.map((e) => {
                const value = typeof e.value === "number" ? Math.round(e.value * 100) : undefined;
                let text: string;
                try {
                  text = codes(e.code as "name_similarity", { value: value ?? 0 });
                } catch {
                  text = e.code;
                }
                return (
                  <li key={e.code} className="flex items-center justify-between gap-2 text-xs">
                    <span>{text}</span>
                    {e.weight !== 0 ? (
                      <span className={cn("font-mono tnum", e.weight > 0 ? "text-ok" : "text-bad")}>
                        {e.weight > 0 ? "+" : ""}
                        {e.weight.toLocaleString("tr-TR", { maximumFractionDigits: 1 })}
                      </span>
                    ) : null}
                  </li>
                );
              })}
            </ul>
          </div>
        </div>
        <Side side={card.right} showPii={showPii} />
      </div>
    </article>
  );
}

function Side({ side, showPii }: { side: Schemas["CardSide"]; showPii: boolean }) {
  const t = useTranslations("matching");
  const tc = useTranslations("common");
  const entity = side.entity;
  if (!entity) return <div className="p-6" />;
  const totals = Object.entries(entity.totals);

  return (
    <section className="flex min-w-0 flex-col gap-5 p-6 [&+section]:border-t [&+section]:border-rule md:[&+section]:border-t-0 md:[&+section]:border-l xl:[&+section]:border-l-0">
      <div>
        <h2 className="display text-2xl font-semibold">{entity.name}</h2>
        <p className="mt-1 text-sm text-ink-muted tnum">{t("records", { count: entity.record_count })}</p>
      </div>

      <div>
        <p className="mb-1.5 text-xs font-medium text-ink-faint">{t("aliases")}</p>
        <div className="flex flex-wrap gap-1.5">
          {entity.aliases.map((a) => (
            <Badge key={a.name} tone="outline" className="text-[13px]">
              {a.name}
              <span className="text-ink-faint tnum">×{a.count}</span>
            </Badge>
          ))}
        </div>
      </div>

      <dl className="grid grid-cols-2 gap-x-4 gap-y-3 text-sm">
        <div>
          <dt className="text-xs text-ink-faint">{t("phones")}</dt>
          <dd className="mt-0.5 flex flex-col tnum">
            {entity.phones.length ? (
              entity.phones.map((p) => (
                <span key={p} className="inline-flex items-center gap-1.5">
                  <Phone className="size-3 text-ink-faint" />
                  {showPii ? p : maskPii(p, "phone")}
                </span>
              ))
            ) : (
              <span className="text-ink-faint">{t("noPhone")}</span>
            )}
          </dd>
        </div>
        <div>
          <dt className="text-xs text-ink-faint">{t("period")}</dt>
          <dd className="mt-0.5 tnum">
            {entity.first_date ? formatDate(entity.first_date) : "—"}
            {entity.last_date && entity.last_date !== entity.first_date ? ` – ${formatDate(entity.last_date)}` : ""}
          </dd>
        </div>
        {totals.length ? (
          <div className="col-span-2">
            <dt className="text-xs text-ink-faint">{t("totals")}</dt>
            <dd className="mt-0.5 flex flex-wrap gap-x-4 tnum">
              {totals.map(([role, value]) => (
                <span key={role}>
                  <RoleName role={role} />: {formatMoney(value)}
                </span>
              ))}
            </dd>
          </div>
        ) : null}
      </dl>

      <div>
        <p className="mb-1.5 text-xs font-medium text-ink-faint">{t("samples")}</p>
        <ul className="divide-y divide-rule rounded-xl border border-rule bg-paper text-sm">
          {entity.samples.map((s) => {
            const money = s.debit ?? s.amount ?? s.credit;
            return (
              <li key={s.record_id} className="flex items-center gap-3 px-3 py-2">
                <span className="w-20 shrink-0 text-xs text-ink-faint tnum">{s.date ? formatDate(s.date) : "—"}</span>
                <span className="min-w-0 flex-1 truncate">{s.name}</span>
                {money != null ? <span className="tnum">{formatMoney(money)}</span> : null}
                <span className="hidden font-mono text-[11px] text-ink-faint sm:inline" title={s.filename ?? ""}>
                  {s.row ? tc("rowShort", { row: s.row }) : ""}
                </span>
              </li>
            );
          })}
        </ul>
      </div>
    </section>
  );
}

function RoleName({ role }: { role: string }) {
  const t = useTranslations("roles");
  return <>{t(role as "amount")}</>;
}
