import { AskView } from "@/features/ask/ask-view";

export default async function AskPage({ params }: { params: Promise<{ ws: string }> }) {
  return <AskView ws={Number((await params).ws)} />;
}
