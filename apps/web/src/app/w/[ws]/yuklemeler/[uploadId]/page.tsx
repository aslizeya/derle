import { ReviewView } from "@/features/review/review-view";

export default async function ReviewPage({
  params,
}: {
  params: Promise<{ ws: string; uploadId: string }>;
}) {
  const { ws, uploadId } = await params;
  return <ReviewView ws={Number(ws)} uploadId={Number(uploadId)} />;
}
