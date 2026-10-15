"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useRef, useState } from "react";

import {
  type PipelineEvent,
  type UploadResult,
  UploadError,
  uploadWithEvents,
} from "@/lib/api/stream";

export type UploadStatus = "queued" | "processing" | "done" | "failed";

export type UploadJob = {
  id: string;
  file: File;
  status: UploadStatus;
  events: PipelineEvent[];
  result?: UploadResult;
  error?: string;
};

let counter = 0;

/** Processes dropped files one at a time (DuckDB has a single writer) and keeps their events. */
export function useUploadQueue(workspaceId: number) {
  const [jobs, setJobs] = useState<UploadJob[]>([]);
  const pending = useRef<UploadJob[]>([]);
  const running = useRef(false);
  const queryClient = useQueryClient();

  const update = useCallback((id: string, patch: (job: UploadJob) => Partial<UploadJob>) => {
    setJobs((all) => all.map((job) => (job.id === id ? { ...job, ...patch(job) } : job)));
  }, []);

  const drain = useCallback(async () => {
    if (running.current) return;
    running.current = true;
    try {
      for (let job = pending.current.shift(); job; job = pending.current.shift()) {
        const id = job.id;
        update(id, () => ({ status: "processing" }));
        try {
          const result = await uploadWithEvents(workspaceId, job.file, {
            onEvent: (event) => update(id, (current) => ({ events: [...current.events, event] })),
          });
          update(id, () => ({ status: "done", result }));
        } catch (error) {
          const code = error instanceof UploadError ? error.code : "internal_error";
          update(id, () => ({ status: "failed", error: code }));
        }
        void queryClient.invalidateQueries();
      }
    } finally {
      running.current = false;
    }
  }, [update, workspaceId, queryClient]);

  const enqueue = useCallback(
    (files: File[]) => {
      const added = files.map((file) => ({
        id: `${Date.now()}-${counter++}`,
        file,
        status: "queued" as const,
        events: [],
      }));
      setJobs((all) => [...all, ...added]);
      pending.current.push(...added);
      void drain();
    },
    [drain],
  );

  const busy = jobs.some((job) => job.status === "queued" || job.status === "processing");
  return { jobs, enqueue, busy };
}
