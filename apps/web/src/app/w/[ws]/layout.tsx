import { notFound } from "next/navigation";

import { AppShell } from "@/components/app-shell";

export default async function WorkspaceLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ ws: string }>;
}) {
  const ws = Number((await params).ws);
  if (!Number.isInteger(ws) || ws <= 0) notFound();
  return <AppShell ws={ws}>{children}</AppShell>;
}
