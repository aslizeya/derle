"use client";

import {
  BarChart3,
  GitMerge,
  History,
  LayoutGrid,
  Menu,
  MessageCircleQuestion,
  Table2,
  Upload,
  type LucideIcon,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { Logo, ThemeToggle } from "@/components/brand";
import { Badge } from "@/components/ui/badge";
import { Sheet } from "@/components/ui/sheet";
import { useDatasets, useWorkspace } from "@/lib/api/hooks";
import { cn } from "@/lib/utils";

type NavItem = {
  href: string;
  label: string;
  icon: LucideIcon;
  badge?: number;
  match: string;
  mobile?: boolean; // shown in the phone tab bar; the rest live under "more"
};

export function AppShell({ ws, children }: { ws: number; children: React.ReactNode }) {
  const t = useTranslations("nav");
  const tApp = useTranslations("app");
  const pathname = usePathname();
  const workspace = useWorkspace(ws);
  const datasets = useDatasets(ws);
  const [moreOpen, setMoreOpen] = useState(false);
  const base = `/w/${ws}`;
  const largest = [...(datasets.data ?? [])].sort((a, b) => b.records - a.records)[0];

  const items: NavItem[] = [
    { href: base, label: t("workspace"), icon: LayoutGrid, match: `${base}$`, mobile: true },
    { href: `${base}/yukle`, label: t("upload"), icon: Upload, match: `${base}/(yukle|yuklemeler)` },
    {
      href: `${base}/eslestirme`,
      label: t("matching"),
      icon: GitMerge,
      badge: workspace.data?.pending_matches,
      match: `${base}/eslestirme`,
      mobile: true,
    },
    {
      href: largest ? `${base}/veri/${largest.id}` : base,
      label: t("data"),
      icon: Table2,
      match: `${base}/veri`,
      mobile: true,
    },
    { href: `${base}/panel`, label: t("dashboard"), icon: BarChart3, match: `${base}/panel` },
    { href: `${base}/sor`, label: t("ask"), icon: MessageCircleQuestion, match: `${base}/sor`, mobile: true },
    { href: `${base}/gecmis`, label: t("history"), icon: History, match: `${base}/gecmis` },
  ];
  const isActive = (item: NavItem) => new RegExp(`^${item.match}`).test(pathname);
  const moreActive = items.some((i) => !i.mobile && isActive(i));

  const link = (item: NavItem, onClick?: () => void) => (
    <Link
      key={item.label}
      href={item.href}
      onClick={onClick}
      aria-current={isActive(item) ? "page" : undefined}
      className={cn(
        "flex items-center gap-3 rounded-lg px-3 py-2 text-sm text-ink-muted transition-colors hover:bg-paper-sunken hover:text-ink",
        isActive(item) && "bg-accent-soft font-medium text-accent hover:bg-accent-soft hover:text-accent",
      )}
    >
      <item.icon className="size-4" />
      <span className="flex-1">{item.label}</span>
      {item.badge ? <Badge tone="warn">{item.badge}</Badge> : null}
    </Link>
  );

  return (
    <div className="min-h-dvh md:grid md:grid-cols-[232px_1fr]">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-50 focus:rounded-lg focus:bg-paper-raised focus:px-3 focus:py-2"
      >
        {tApp("skipToContent")}
      </a>

      {/* Desktop sidebar */}
      <aside className="sticky top-0 hidden h-dvh flex-col border-r border-rule bg-paper-raised/60 px-4 py-5 md:flex">
        <Logo href="/" />
        <div className="mt-6 mb-4 min-h-10">
          <p className="truncate text-sm font-medium" title={workspace.data?.name}>
            {workspace.data?.name ?? " "}
          </p>
          {workspace.data?.is_demo ? (
            <Badge tone="accent" className="mt-1">
              {t("demoBadge")}
            </Badge>
          ) : null}
        </div>
        <nav className="flex flex-col gap-1" aria-label={t("menu")}>
          {items.slice(0, 4).map((item) => link(item))}
          <div className="my-2 border-t border-rule" />
          {items.slice(4).map((item) => link(item))}
        </nav>
        <div className="mt-auto flex items-center justify-between">
          <ThemeToggle />
        </div>
      </aside>

      {/* Mobile top bar */}
      <header className="sticky top-0 z-30 flex items-center justify-between border-b border-rule bg-paper/90 px-4 py-3 backdrop-blur md:hidden">
        <Logo href="/" />
        <ThemeToggle />
      </header>

      <main id="main" className="min-w-0 px-4 pt-6 pb-28 md:px-10 md:pt-10 md:pb-16">
        {children}
      </main>

      {/* Mobile bottom tab bar */}
      <nav
        className="fixed inset-x-0 bottom-0 z-30 grid grid-cols-5 border-t border-rule bg-paper-raised/95 pb-[env(safe-area-inset-bottom)] backdrop-blur md:hidden"
        aria-label={t("menu")}
      >
        {items
          .filter((item) => item.mobile)
          .map((item) => (
            <Link
              key={item.label}
              href={item.href}
              aria-current={isActive(item) ? "page" : undefined}
              className={cn(
                "relative flex flex-col items-center gap-1 py-2.5 text-[11px] text-ink-muted",
                isActive(item) && "text-accent",
              )}
            >
              <item.icon className="size-5" />
              {item.label}
              {item.badge ? (
                <span className="absolute top-1.5 left-1/2 ml-2 min-w-4 rounded-full bg-warn px-1 text-[10px] leading-4 text-paper tnum">
                  {item.badge}
                </span>
              ) : null}
            </Link>
          ))}
        <button
          type="button"
          onClick={() => setMoreOpen(true)}
          className={cn(
            "flex flex-col items-center gap-1 py-2.5 text-[11px] text-ink-muted",
            moreActive && "text-accent",
          )}
        >
          <Menu className="size-5" />
          {t("more")}
        </button>
      </nav>
      <Sheet open={moreOpen} onOpenChange={setMoreOpen} title={t("menu")}>
        <nav className="flex flex-col gap-1">{items.map((item) => link(item, () => setMoreOpen(false)))}</nav>
      </Sheet>
    </div>
  );
}
