import type { Schemas } from "./client";

export type PipelineEvent = Schemas["PipelineEvent"];
export type UploadResult = Schemas["UploadOut"];

export type StreamHandlers = {
  onEvent: (event: PipelineEvent) => void;
  signal?: AbortSignal;
};

export class UploadError extends Error {
  constructor(
    readonly code: string,
    readonly uploadId: number | null = null,
  ) {
    super(code);
  }
}

/**
 * Upload a file and follow the pipeline live. The endpoint answers with Server-Sent Events
 * (`event`, then `result` or `error`); EventSource cannot POST, so we read the stream by hand.
 */
export async function uploadWithEvents(
  workspaceId: number,
  file: File,
  { onEvent, signal }: StreamHandlers,
): Promise<UploadResult> {
  const body = new FormData();
  body.append("file", file);
  let response: Response;
  try {
    response = await fetch(`/api/v1/workspaces/${workspaceId}/uploads/stream`, {
      method: "POST",
      body,
      signal,
    });
  } catch {
    throw new UploadError("network");
  }
  if (!response.ok || !response.body) {
    const detail = (await response.json().catch(() => null)) as { detail?: { code?: string } } | null;
    throw new UploadError(detail?.detail?.code ?? "internal_error");
  }

  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += value;
    let boundary: number;
    while ((boundary = buffer.indexOf("\n\n")) !== -1) {
      const block = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      const { event, data } = parseBlock(block);
      if (event === "event") onEvent(data as PipelineEvent);
      else if (event === "result") return data as UploadResult;
      else if (event === "error") {
        const error = data as { code: string; upload_id: number | null };
        throw new UploadError(error.code, error.upload_id);
      }
    }
  }
  throw new UploadError("internal_error");
}

function parseBlock(block: string): { event: string; data: unknown } {
  let event = "message";
  const data: string[] = [];
  for (const line of block.split("\n")) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) data.push(line.slice(5).trimStart());
  }
  return { event, data: JSON.parse(data.join("\n")) };
}
