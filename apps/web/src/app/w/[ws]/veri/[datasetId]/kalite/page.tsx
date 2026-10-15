import { QualityView } from "@/features/quality/quality-view";

export default async function QualityPage({
  params,
}: {
  params: Promise<{ ws: string; datasetId: string }>;
}) {
  const { ws, datasetId } = await params;
  return <QualityView ws={Number(ws)} datasetId={Number(datasetId)} />;
}
