import type {
  Contradiction,
  GraphEntityDetail,
  GraphBuildResult,
  GraphVisualization,
  QueryResult,
  SourceIngestResult,
  SourceRef,
} from "../domain/models";
import type { ApiClient, QueryInput, UploadSourceInput } from "./apiClient";

export interface WorkbenchGateway {
  listSources(): Promise<SourceRef[]>;
  uploadSource(input: UploadSourceInput): Promise<SourceRef>;
  ingestSource(sourceId: string): Promise<SourceIngestResult>;
  buildGraph(sourceIds?: string[]): Promise<GraphBuildResult>;
  ask(input: QueryInput): Promise<QueryResult>;
  graph(query: string): Promise<GraphVisualization>;
  entity(entityIdOrName: string): Promise<GraphEntityDetail>;
  contradictions(): Promise<Contradiction[]>;
}

export class WorkbenchService implements WorkbenchGateway {
  constructor(private readonly apiClient: ApiClient) {}

  listSources(): Promise<SourceRef[]> {
    return this.apiClient.listSources();
  }

  uploadSource(input: UploadSourceInput): Promise<SourceRef> {
    return this.apiClient.uploadSource(input);
  }

  ingestSource(sourceId: string): Promise<SourceIngestResult> {
    return this.apiClient.ingestSource(sourceId);
  }

  buildGraph(sourceIds: string[] = []): Promise<GraphBuildResult> {
    return this.apiClient.buildGraph(sourceIds);
  }

  ask(input: QueryInput): Promise<QueryResult> {
    return this.apiClient.ask(input);
  }

  graph(query: string): Promise<GraphVisualization> {
    return this.apiClient.getGraphVisualization(query);
  }

  entity(entityIdOrName: string): Promise<GraphEntityDetail> {
    return this.apiClient.getEntityDetail(entityIdOrName);
  }

  contradictions(): Promise<Contradiction[]> {
    return this.apiClient.listContradictions();
  }
}
