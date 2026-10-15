import { TableView } from "@/features/table/table-view";

export default async function DatasetPage({
  params,
  searchParams,
}: {
  params: Promise<{ ws: string; datasetId: string }>;
  searchParams: Promise<{ sort?: string; desc?: string }>;
}) {
  const [{ ws, datasetId }, { sort, desc }] = await Promise.all([params, searchParams]);
  return (
    <TableView
      ws={Number(ws)}
      datasetId={Number(datasetId)}
      initialSort={sort ? { id: sort, desc: desc === "1" } : undefined}
    />
  );
}
