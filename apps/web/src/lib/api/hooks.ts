"use client";

import {
  keepPreviousData,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";

import { api, unwrap } from "./client";

export const keys = {
  workspace: (ws: number) => ["workspace", ws] as const,
  datasets: (ws: number) => ["datasets", ws] as const,
  uploads: (ws: number) => ["uploads", ws] as const,
  upload: (id: number) => ["upload", id] as const,
  diff: (table: number, limit: number) => ["diff", table, limit] as const,
  transforms: (table: number) => ["transforms", table] as const,
  dataset: (id: number) => ["dataset", id] as const,
  records: (id: number, params: object) => ["records", id, params] as const,
  provenance: (record: number, field: number) => ["provenance", record, field] as const,
  matches: (ws: number) => ["matches", ws] as const,
};

export function useWorkspace(ws: number) {
  return useQuery({
    queryKey: keys.workspace(ws),
    queryFn: async () =>
      unwrap(await api.GET("/api/v1/workspaces/{workspace_id}", { params: { path: { workspace_id: ws } } })),
  });
}

export function useDatasets(ws: number) {
  return useQuery({
    queryKey: keys.datasets(ws),
    queryFn: async () =>
      unwrap(
        await api.GET("/api/v1/workspaces/{workspace_id}/datasets", {
          params: { path: { workspace_id: ws } },
        }),
      ),
  });
}

export function useUploads(ws: number) {
  return useQuery({
    queryKey: keys.uploads(ws),
    queryFn: async () =>
      unwrap(
        await api.GET("/api/v1/workspaces/{workspace_id}/uploads", {
          params: { path: { workspace_id: ws } },
        }),
      ),
  });
}

export function useUpload(id: number) {
  return useQuery({
    queryKey: keys.upload(id),
    queryFn: async () =>
      unwrap(await api.GET("/api/v1/uploads/{upload_id}", { params: { path: { upload_id: id } } })),
  });
}

export function useTableDiff(table: number | undefined, limit: number) {
  return useQuery({
    queryKey: keys.diff(table ?? 0, limit),
    enabled: table !== undefined,
    placeholderData: keepPreviousData,
    queryFn: async () =>
      unwrap(
        await api.GET("/api/v1/tables/{table_id}/diff", {
          params: { path: { table_id: table! }, query: { limit, offset: 0 } },
        }),
      ),
  });
}

export function useTransformations(table: number | undefined) {
  return useQuery({
    queryKey: keys.transforms(table ?? 0),
    enabled: table !== undefined,
    queryFn: async () =>
      unwrap(
        await api.GET("/api/v1/tables/{table_id}/transformations", {
          params: { path: { table_id: table! }, query: { limit: 500 } },
        }),
      ),
  });
}

export function useDataset(id: number) {
  return useQuery({
    queryKey: keys.dataset(id),
    queryFn: async () =>
      unwrap(await api.GET("/api/v1/datasets/{dataset_id}", { params: { path: { dataset_id: id } } })),
  });
}

export type RecordQuery = { limit: number; offset: number; sort?: string; desc?: boolean; q?: string };

export function useRecords(id: number, query: RecordQuery) {
  return useQuery({
    queryKey: keys.records(id, query),
    placeholderData: keepPreviousData,
    queryFn: async () =>
      unwrap(
        await api.GET("/api/v1/datasets/{dataset_id}/records", {
          params: { path: { dataset_id: id }, query: { ...query, q: query.q || undefined } },
        }),
      ),
  });
}

export function useProvenance(record: number | undefined, field: number | undefined) {
  return useQuery({
    queryKey: keys.provenance(record ?? 0, field ?? 0),
    enabled: record !== undefined && field !== undefined,
    queryFn: async () =>
      unwrap(
        await api.GET("/api/v1/records/{record_id}/cells/{field_id}/provenance", {
          params: { path: { record_id: record!, field_id: field! } },
        }),
      ),
  });
}

export function useMatches(ws: number) {
  return useQuery({
    queryKey: keys.matches(ws),
    queryFn: async () =>
      unwrap(
        await api.GET("/api/v1/workspaces/{workspace_id}/matches", {
          params: { path: { workspace_id: ws }, query: { limit: 5 } },
        }),
      ),
  });
}

/** After anything that changes data: refetch everything that may show it. */
function useInvalidateAll() {
  const client = useQueryClient();
  return () => client.invalidateQueries();
}

export function useDecideMatch() {
  const invalidate = useInvalidateAll();
  return useMutation({
    mutationFn: async (vars: { id: number; decision: "same" | "different" | "skip" }) =>
      unwrap(
        await api.POST("/api/v1/matches/{candidate_id}/decision", {
          params: { path: { candidate_id: vars.id } },
          body: { decision: vars.decision },
        }),
      ),
    onSuccess: invalidate,
  });
}

export function useUndoMatch(ws: number) {
  const invalidate = useInvalidateAll();
  return useMutation({
    mutationFn: async () =>
      unwrap(
        await api.POST("/api/v1/workspaces/{workspace_id}/matches/undo", {
          params: { path: { workspace_id: ws } },
        }),
      ),
    onSuccess: invalidate,
  });
}

export function useUndoTransformation() {
  const invalidate = useInvalidateAll();
  return useMutation({
    mutationFn: async (id: number) =>
      unwrap(
        await api.POST("/api/v1/transformations/{transformation_id}/undo", {
          params: { path: { transformation_id: id } },
        }),
      ),
    onSuccess: invalidate,
  });
}

export function useUndoUpload() {
  const invalidate = useInvalidateAll();
  return useMutation({
    mutationFn: async (id: number) =>
      unwrap(
        await api.POST("/api/v1/uploads/{upload_id}/undo", { params: { path: { upload_id: id } } }),
      ),
    onSuccess: invalidate,
  });
}

export async function createDemoWorkspace() {
  return unwrap(await api.POST("/api/v1/demo/workspaces"));
}

export async function fetchDemoFiles(): Promise<File[]> {
  const list = unwrap(await api.GET("/api/v1/demo/files"));
  return Promise.all(
    list.map(async ({ name }) => {
      const response = await fetch(`/api/v1/demo/files/${encodeURIComponent(name)}`);
      if (!response.ok) throw new Error(`demo file ${name}: ${response.status}`);
      return new File([await response.blob()], name);
    }),
  );
}

// --- analytics ------------------------------------------------------------------------------

export function useQuality(datasetId: number | undefined) {
  return useQuery({
    queryKey: ["quality", datasetId],
    enabled: datasetId !== undefined,
    queryFn: async () =>
      unwrap(
        await api.GET("/api/v1/datasets/{dataset_id}/quality", {
          params: { path: { dataset_id: datasetId! } },
        }),
      ),
  });
}

export function useDashboard(datasetId: number | undefined) {
  return useQuery({
    queryKey: ["dashboard", datasetId],
    enabled: datasetId !== undefined,
    queryFn: async () =>
      unwrap(
        await api.GET("/api/v1/datasets/{dataset_id}/dashboard", {
          params: { path: { dataset_id: datasetId! } },
        }),
      ),
  });
}

export function useAsk(ws: number) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (vars: { question: string; datasetId?: number }) =>
      unwrap(
        await api.POST("/api/v1/workspaces/{workspace_id}/ask", {
          params: { path: { workspace_id: ws } },
          body: { question: vars.question, dataset_id: vars.datasetId ?? null },
        }),
      ),
    onSuccess: () => client.invalidateQueries({ queryKey: ["questions", ws] }),
  });
}

export function useRecentQuestions(ws: number) {
  return useQuery({
    queryKey: ["questions", ws],
    queryFn: async () =>
      unwrap(
        await api.GET("/api/v1/workspaces/{workspace_id}/questions", {
          params: { path: { workspace_id: ws } },
        }),
      ),
  });
}

export function useVersions(ws: number) {
  return useQuery({
    queryKey: ["versions", ws],
    queryFn: async () =>
      unwrap(
        await api.GET("/api/v1/workspaces/{workspace_id}/versions", {
          params: { path: { workspace_id: ws } },
        }),
      ),
  });
}

export function useRestore(ws: number) {
  const invalidate = useInvalidateAll();
  return useMutation({
    mutationFn: async (versionId: number) =>
      unwrap(
        await api.POST("/api/v1/workspaces/{workspace_id}/versions/{version_id}/restore", {
          params: { path: { workspace_id: ws, version_id: versionId } },
        }),
      ),
    onSuccess: invalidate,
  });
}

export function useRenameDataset() {
  const invalidate = useInvalidateAll();
  return useMutation({
    mutationFn: async (vars: { id: number; name: string }) =>
      unwrap(
        await api.PATCH("/api/v1/datasets/{dataset_id}", {
          params: { path: { dataset_id: vars.id } },
          body: { name: vars.name },
        }),
      ),
    onSuccess: invalidate,
  });
}

export function exportUrl(datasetId: number, format: "xlsx" | "csv", mask: boolean): string {
  return `/api/v1/datasets/${datasetId}/export?format=${format}&mask=${mask}`;
}
