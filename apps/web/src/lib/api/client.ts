import createClient from "openapi-fetch";

import type { components, paths } from "./schema";

/** Typed client for the FastAPI backend. Requests go to this origin and are proxied. */
export const api = createClient<paths>({ baseUrl: "" });

export type Schemas = components["schemas"];

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
  ) {
    super(code);
  }
}

type Result<T> = { data?: T; error?: unknown; response: Response };

/** Unwrap an openapi-fetch result, turning `{detail: {code}}` errors into ApiError. */
export function unwrap<T>({ data, error, response }: Result<T>): T {
  if (error !== undefined || data === undefined) {
    const detail = (error as { detail?: { code?: string } } | undefined)?.detail;
    throw new ApiError(response.status, detail?.code ?? `http_${response.status}`);
  }
  return data;
}
