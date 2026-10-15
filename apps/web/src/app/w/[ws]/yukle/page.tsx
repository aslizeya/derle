import { UploadView } from "@/features/upload/upload-view";

export default async function UploadPage({
  params,
  searchParams,
}: {
  params: Promise<{ ws: string }>;
  searchParams: Promise<{ ornek?: string }>;
}) {
  const [{ ws }, { ornek }] = await Promise.all([params, searchParams]);
  return <UploadView workspaceId={Number(ws)} demo={ornek === "1"} />;
}
