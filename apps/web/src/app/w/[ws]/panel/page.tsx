import { DashboardView } from "@/features/dashboard/dashboard-view";

export default async function DashboardPage({ params }: { params: Promise<{ ws: string }> }) {
  return <DashboardView ws={Number((await params).ws)} />;
}
