import {
  Calendar,
  CircleHelp,
  CreditCard,
  Hash,
  IdCard,
  Mail,
  MessageSquareText,
  Minus,
  Phone,
  Plus,
  Scale,
  Tag,
  User,
  Wallet,
  type LucideIcon,
} from "lucide-react";

export const ROLE_ICONS: Record<string, LucideIcon> = {
  party: User,
  first_name: User,
  last_name: User,
  date: Calendar,
  amount: Wallet,
  debit: Plus,
  credit: Minus,
  balance: Scale,
  quantity: Hash,
  phone: Phone,
  tckn: IdCard,
  email: Mail,
  description: MessageSquareText,
  category: Tag,
  identifier: Hash,
  unknown: CircleHelp,
};

export function RoleIcon({ role, className }: { role: string; className?: string }) {
  const Icon = ROLE_ICONS[role] ?? CreditCard;
  return <Icon className={className ?? "size-4"} aria-hidden />;
}

export const KNOWN_ROLES = new Set(Object.keys(ROLE_ICONS));
export const KNOWN_TRANSFORMS = new Set([
  "date_parsed",
  "number_parsed",
  "currency_stripped",
  "honorific_removed",
  "name_normalized",
  "names_combined",
  "phone_normalized",
  "text_trimmed",
  "parse_failed",
  "duplicate_removed",
]);
