import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

const LOCALE = "tr-TR";

const money = new Intl.NumberFormat(LOCALE, {
  style: "currency",
  currency: "TRY",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});
const number = new Intl.NumberFormat(LOCALE, { maximumFractionDigits: 4 });
const shortDate = new Intl.DateTimeFormat(LOCALE, {
  day: "numeric",
  month: "short",
  year: "numeric",
  timeZone: "UTC",
});
const dateTime = new Intl.DateTimeFormat(LOCALE, {
  day: "numeric",
  month: "long",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
});

export const MONEY_ROLES = new Set(["amount", "debit", "credit", "balance"]);

export function formatMoney(value: number): string {
  return money.format(value);
}

export function formatNumber(value: number): string {
  return number.format(value);
}

/** "2026-03-15" → "15 Mar 2026". Date-only strings are treated as calendar dates (UTC). */
export function formatDate(iso: string): string {
  const date = new Date(iso.length === 10 ? `${iso}T00:00:00Z` : iso);
  return Number.isNaN(date.getTime()) ? iso : shortDate.format(date);
}

export function formatDateTime(iso: string): string {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? iso : dateTime.format(date);
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${number.format(Math.round(bytes / 102.4) / 10)} KB`;
  return `${number.format(Math.round(bytes / 104857.6) / 10)} MB`;
}

/** "0532 123 45 67" → "0532 *** ** 67"; TCKN "10000000146" → "100******46". */
export function maskPii(value: string, kind: string | null | undefined): string {
  if (kind === "phone") {
    const parts = value.split(" ");
    return parts.length === 4 ? `${parts[0]} *** ** ${parts[3]}` : value.replace(/\d(?=\d{2})/g, "*");
  }
  if (kind === "tckn" && value.length === 11) return `${value.slice(0, 3)}******${value.slice(-2)}`;
  if (kind === "email") {
    const [user = "", domain = ""] = value.split("@");
    return `${user.slice(0, 1)}***@${domain}`;
  }
  return value;
}
