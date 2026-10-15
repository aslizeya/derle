import { HistoryView } from "@/features/history/history-view";

export default async function HistoryPage({ params }: { params: Promise<{ ws: string }> }) {
  return <HistoryView ws={Number((await params).ws)} />;
}
