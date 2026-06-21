import type {
  QueryResult,
  SourceIngestResult,
  SourceRef,
  WikiPage,
  WikiPageSummary,
} from "../domain/models";

export interface UploadSourceInput {
  file: File;
  title?: string;
  sourceType?: string;
  tags?: string[];
}

export interface QueryInput {
  question: string;
  mode?: "fast" | "deep" | "audit";
  sourceIds?: string[];
}

export interface ApiClientOptions {
  baseUrl: string;
  fetcher?: typeof fetch;
}

export class ApiClient {
  private readonly baseUrl: string;
  private readonly fetcher: typeof fetch;

  constructor(options: ApiClientOptions) {
    this.baseUrl = options.baseUrl.replace(/\/$/, "");
    this.fetcher = options.fetcher ?? fetch.bind(globalThis);
  }

  listSources(): Promise<SourceRef[]> {
    return this.request<SourceRef[]>("/sources");
  }

  async uploadSource(input: UploadSourceInput): Promise<SourceRef> {
    const form = new FormData();
    form.append("file", input.file);
    if (input.title?.trim()) form.append("title", input.title.trim());
    if (input.sourceType?.trim()) form.append("source_type", input.sourceType.trim());
    for (const tag of input.tags ?? []) {
      if (tag.trim()) form.append("tags", tag.trim());
    }
    return this.request<SourceRef>("/sources/upload", { method: "POST", body: form });
  }

  ingestSource(sourceId: string): Promise<SourceIngestResult> {
    return this.request<SourceIngestResult>(
      `/sources/${encodeURIComponent(sourceId)}/ingest`,
      { method: "POST" },
    );
  }

  ask(input: QueryInput): Promise<QueryResult> {
    return this.request<QueryResult>("/query", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        question: input.question,
        mode: input.mode ?? "deep",
        source_ids: input.sourceIds ?? [],
      }),
    });
  }

  listPages(): Promise<WikiPageSummary[]> {
    return this.request<WikiPageSummary[]>("/wiki/pages");
  }

  getPage(pageId: string): Promise<WikiPage> {
    return this.request<WikiPage>(`/wiki/pages/${encodeURIComponent(pageId)}`);
  }

  rebuildWiki(): Promise<WikiPageSummary[]> {
    return this.request<WikiPageSummary[]>("/wiki/rebuild", { method: "POST" });
  }

  private async request<T>(path: string, init?: RequestInit): Promise<T> {
    const response = await this.fetcher(`${this.baseUrl}${path}`, init);
    if (!response.ok) {
      throw new ApiError(response.status, await extractErrorMessage(response));
    }
    return (await response.json()) as T;
  }
}

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function extractErrorMessage(response: Response): Promise<string> {
  try {
    const payload = (await response.json()) as { detail?: unknown };
    return typeof payload.detail === "string"
      ? payload.detail
      : JSON.stringify(payload.detail ?? payload);
  } catch {
    return response.statusText || "Request failed";
  }
}

export function createDefaultApiClient(): ApiClient {
  return new ApiClient({ baseUrl: import.meta.env.VITE_API_BASE_URL || "/api" });
}
