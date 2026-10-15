import * as React from "react";

import { cn } from "@/lib/utils";

export function Kbd({ className, ...props }: React.HTMLAttributes<HTMLElement>) {
  return (
    <kbd
      className={cn(
        "inline-flex h-5 min-w-5 items-center justify-center rounded border border-rule-strong border-b-2 bg-paper px-1 font-mono text-[11px] font-medium text-ink-muted",
        className,
      )}
      {...props}
    />
  );
}

export function Skeleton({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("animate-pulse rounded-md bg-paper-sunken", className)} {...props} />;
}

export function Input({ className, ...props }: React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className={cn(
        "h-10 w-full rounded-lg border border-rule-strong bg-paper-raised px-3 text-sm text-ink placeholder:text-ink-faint focus:border-accent focus:outline-none",
        className,
      )}
      {...props}
    />
  );
}

/** Ring that shows a 0–1 confidence or similarity value. */
export function ScoreRing({
  value,
  size = 44,
  className,
}: {
  value: number;
  size?: number;
  className?: string;
}) {
  const stroke = 4;
  const radius = (size - stroke) / 2;
  const circumference = 2 * Math.PI * radius;
  const pct = Math.round(value * 100);
  const tone = value >= 0.9 ? "var(--ok)" : value >= 0.6 ? "var(--accent)" : "var(--warn)";
  return (
    <div className={cn("relative inline-grid place-items-center", className)} style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90" aria-hidden>
        <circle cx={size / 2} cy={size / 2} r={radius} fill="none" stroke="var(--rule)" strokeWidth={stroke} />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={tone}
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={circumference * (1 - value)}
          style={{ transition: "stroke-dashoffset 0.6s ease" }}
        />
      </svg>
      <span className="absolute text-[11px] font-semibold tnum">{pct}</span>
    </div>
  );
}

export function EmptyState({
  icon,
  title,
  body,
  children,
  className,
}: {
  icon: React.ReactNode;
  title: string;
  body?: string;
  children?: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "ruled flex flex-col items-center rounded-2xl border border-dashed border-rule-strong px-6 py-14 text-center",
        className,
      )}
    >
      <div className="mb-4 grid size-12 place-items-center rounded-full bg-accent-soft text-accent [&_svg]:size-6">
        {icon}
      </div>
      <h2 className="display text-xl font-semibold">{title}</h2>
      {body ? <p className="mt-2 max-w-md text-sm leading-relaxed text-ink-muted">{body}</p> : null}
      {children ? <div className="mt-6 flex flex-wrap justify-center gap-2">{children}</div> : null}
    </div>
  );
}

export function ErrorState({
  title,
  body,
  onRetry,
  retryLabel,
}: {
  title: string;
  body?: string;
  onRetry?: () => void;
  retryLabel?: string;
}) {
  return (
    <div role="alert" className="rounded-2xl border border-bad/30 bg-bad-soft px-5 py-4 text-sm">
      <p className="font-medium text-bad">{title}</p>
      {body ? <p className="mt-1 text-ink-muted">{body}</p> : null}
      {onRetry ? (
        <button type="button" onClick={onRetry} className="mt-3 font-medium text-accent hover:underline">
          {retryLabel}
        </button>
      ) : null}
    </div>
  );
}
