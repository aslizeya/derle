import { MatchingView } from "@/features/matching/matching-view";

export default async function MatchingPage({ params }: { params: Promise<{ ws: string }> }) {
  return <MatchingView ws={Number((await params).ws)} />;
}
