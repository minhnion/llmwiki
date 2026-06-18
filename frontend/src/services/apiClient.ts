import type {
  Contradiction,
  GraphBuildResult,
  GraphEntityDetail,
  GraphVisualization,
  QueryResult,
  SourceIngestResult,
  SourceRef,
} from "../domain/models";

export interface UploadSourceInput {
  file: File;
  title?: string;
  sourceType?: string;
  tags?: string[];
}

export interface QueryInput {
  question: string;
  mode?: string;
  sourceIds?: string[];
  tags?: string[];
  maxCandidates?: number;
  maxEvidence?: number;
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

  async listSources(): Promise<SourceRef[]> {
    return this.request<SourceRef[]>("/sources");
  }

  async uploadSource(input: UploadSourceInput): Promise<SourceRef> {
    const form = new FormData();
    form.append("file", input.file);
    if (input.title?.trim()) {
      form.append("title", input.title.trim());
    }
    if (input.sourceType?.trim()) {
      form.append("source_type", input.sourceType.trim());
    }
    for (const tag of input.tags ?? []) {
      if (tag.trim()) {
        form.append("tags", tag.trim());
      }
    }
    return this.request<SourceRef>("/sources/upload", {
      method: "POST",
      body: form,
    });
  }

  async ingestSource(sourceId: string): Promise<SourceIngestResult> {
    return this.request<SourceIngestResult>(`/sources/${encodeURIComponent(sourceId)}/ingest`, {
      method: "POST",
    });
  }

  async ask(input: QueryInput): Promise<QueryResult> {
    return this.request<QueryResult>("/query", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        question: input.question,
        mode: input.mode ?? "deep",
        source_ids: input.sourceIds ?? [],
        tags: input.tags ?? [],
        max_candidates: input.maxCandidates ?? 24,
        max_evidence: input.maxEvidence ?? 8,
      }),
    });
  }

  async buildGraph(sourceIds: string[] = []): Promise<GraphBuildResult> {
    return this.request<GraphBuildResult>("/graph/build", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ source_ids: sourceIds, rebuild: true }),
    });
  }

  async getGraphVisualization(query = "", limit = 80): Promise<GraphVisualization> {
    const params = new URLSearchParams({ limit: String(limit) });
    if (query.trim()) {
      params.set("q", query.trim());
    }
    return this.request<GraphVisualization>(`/graph/visualization?${params.toString()}`);
  }

  async getEntityDetail(entityIdOrName: string): Promise<GraphEntityDetail> {
    return this.request<GraphEntityDetail>(
      `/graph/entities/${encodeURIComponent(entityIdOrName)}`,
    );
  }

  async listContradictions(status = "open"): Promise<Contradiction[]> {
    return this.request<Contradiction[]>(
      `/graph/contradictions?status=${encodeURIComponent(status)}`,
    );
  }

  private async request<T>(path: string, init?: RequestInit): Promise<T> {
    const response = await this.fetcher(`${this.baseUrl}${path}`, init);
    if (!response.ok) {
      const message = await extractErrorMessage(response);
      throw new ApiError(response.status, message);
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
    if (typeof payload.detail === "string") {
      return payload.detail;
    }
    return JSON.stringify(payload.detail ?? payload);
  } catch {
    return response.statusText || "Request failed";
  }
}

export function createDefaultApiClient(): ApiClient {
  const baseUrl = import.meta.env.VITE_API_BASE_URL || "/api";
  return new ApiClient({ baseUrl });
}
