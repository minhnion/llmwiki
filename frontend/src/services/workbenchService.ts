import type {
  QueryResult,
  SourceIngestResult,
  SourceRef,
  WikiPage,
  WikiPageSummary,
} from "../domain/models";
import type { ApiClient, QueryInput, UploadSourceInput } from "./apiClient";

export interface WorkbenchGateway {
  listSources(): Promise<SourceRef[]>;
  uploadSource(input: UploadSourceInput): Promise<SourceRef>;
  ingestSource(sourceId: string): Promise<SourceIngestResult>;
  ask(input: QueryInput): Promise<QueryResult>;
  listPages(): Promise<WikiPageSummary[]>;
  getPage(pageId: string): Promise<WikiPage>;
  rebuildWiki(): Promise<WikiPageSummary[]>;
}

export class WorkbenchService implements WorkbenchGateway {
  constructor(private readonly apiClient: ApiClient) {}

  listSources() {
    return this.apiClient.listSources();
  }

  uploadSource(input: UploadSourceInput) {
    return this.apiClient.uploadSource(input);
  }

  ingestSource(sourceId: string) {
    return this.apiClient.ingestSource(sourceId);
  }

  ask(input: QueryInput) {
    return this.apiClient.ask(input);
  }

  listPages() {
    return this.apiClient.listPages();
  }

  getPage(pageId: string) {
    return this.apiClient.getPage(pageId);
  }

  rebuildWiki() {
    return this.apiClient.rebuildWiki();
  }
}
