import { MONEY_ROLES, formatDate, formatMoney, formatNumber, maskPii } from "@/lib/utils";

export type FieldLike = { role: string; dtype: string; pii?: string | null };

/** Render a clean value for display according to its field. */
export function formatValue(value: unknown, field: FieldLike, maskPersonal = false): string {
  if (value === null || value === undefined || value === "") return "—";
  if (field.dtype === "date" && typeof value === "string") return formatDate(value);
  if (field.dtype === "number" && typeof value === "number") {
    return MONEY_ROLES.has(field.role) ? formatMoney(value) : formatNumber(value);
  }
  const text = String(value);
  return maskPersonal && field.pii ? maskPii(text, field.pii) : text;
}
