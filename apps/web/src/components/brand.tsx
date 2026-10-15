"use client";

import { Monitor, Moon, Sun } from "lucide-react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useTheme } from "next-themes";
import { useSyncExternalStore } from "react";

import { cn } from "@/lib/utils";

/** Wordmark: a stack of three ruled lines straightening out, then "Derle". */
export function Logo({ className, href = "/" }: { className?: string; href?: string }) {
  return (
    <Link href={href} className={cn("group inline-flex items-center gap-2", className)}>
      <svg viewBox="0 0 24 24" className="size-6" aria-hidden>
        <path d="M4 6.5 Q9 4.5 13 7 T20 6" className="stroke-ink-faint" strokeWidth="2" fill="none" strokeLinecap="round" />
        <path d="M4 12 Q11 10.5 20 12.5" className="stroke-ink-muted" strokeWidth="2" fill="none" strokeLinecap="round" />
        <path d="M4 17.5 H20" className="stroke-accent" strokeWidth="2.25" fill="none" strokeLinecap="round" />
      </svg>
      <span className="display text-xl font-semibold tracking-tight">Derle</span>
    </Link>
  );
}

const THEMES = ["light", "dark", "system"] as const;
const ICONS = { light: Sun, dark: Moon, system: Monitor };

export function ThemeToggle({ className }: { className?: string }) {
  const t = useTranslations("common.theme");
  const { theme, setTheme } = useTheme();
  // The stored theme is only known in the browser; render the neutral icon on the server.
  const mounted = useSyncExternalStore(
    () => () => {},
    () => true,
    () => false,
  );

  const current = (mounted && THEMES.includes(theme as (typeof THEMES)[number])
    ? theme
    : "system") as (typeof THEMES)[number];
  const next = THEMES[(THEMES.indexOf(current) + 1) % THEMES.length]!;
  const Icon = ICONS[current];
  return (
    <button
      type="button"
      onClick={() => setTheme(next)}
      className={cn(
        "inline-flex size-9 items-center justify-center rounded-lg text-ink-muted hover:bg-paper-sunken hover:text-ink",
        className,
      )}
      aria-label={`${t("label")}: ${t(current)}`}
      title={`${t("label")}: ${t(current)}`}
    >
      <Icon className="size-4" />
    </button>
  );
}
