import { WorkspaceView } from "@/features/workspace/workspace-view";

export default async function WorkspacePage({ params }: { params: Promise<{ ws: string }> }) {
  return <WorkspaceView ws={Number((await params).ws)} />;
}
