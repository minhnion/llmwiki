import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import App from "./App";
import type {
  QueryResult,
  SourceIngestResult,
  SourceRef,
  WikiPage,
  WikiPageSummary,
} from "./domain/models";
import type { QueryInput, UploadSourceInput } from "./services/apiClient";
import { WorkbenchProvider } from "./services/WorkbenchProvider";
import type { WorkbenchGateway } from "./services/workbenchService";

const source: SourceRef = {
  id: "src_1",
  title: "LLM Wiki Notes",
  path: "/tmp/notes.md",
  source_type: "markdown",
  sha256: "abc",
  mime_type: "text/markdown",
  size_bytes: 1200,
  tags: ["concept"],
  status: "ingested",
  created_at: "2026-06-18T00:00:00Z",
  updated_at: "2026-06-18T00:00:00Z",
  ingested_at: "2026-06-18T00:00:00Z",
};

const pageSummary: WikiPageSummary = {
  id: "page_1",
  path: "/wiki/pages/persistent-wiki.md",
  title: "Persistent Wiki",
  page_type: "knowledge pattern",
  summary: "Knowledge is maintained before query time.",
  status: "active",
  confidence: 0.93,
  source_ids: ["src_1"],
  updated_at: "2026-06-18T00:00:00Z",
};

const page: WikiPage = {
  ...pageSummary,
  body: "# Persistent Wiki\n\nKnowledge compounds across operations.",
  evidence_refs: [
    {
      id: "ev_1",
      source_id: "src_1",
      locator: "section: concept",
      quote_or_summary: "A persistent wiki accumulates knowledge.",
      modality: "text",
      confidence: 0.95,
    },
  ],
  related_page_ids: [],
  created_at: "2026-06-18T00:00:00Z",
};

class FakeWorkbenchService implements WorkbenchGateway {
  listSources = vi.fn<() => Promise<SourceRef[]>>().mockResolvedValue([source]);
  uploadSource = vi
    .fn<(input: UploadSourceInput) => Promise<SourceRef>>()
    .mockResolvedValue(source);
  ingestSource = vi
    .fn<(sourceId: string) => Promise<SourceIngestResult>>()
    .mockResolvedValue({
      source,
      operation_id: "op_1",
      skipped: false,
      changed_page_ids: ["page_1"],
      changed_page_paths: ["pages/persistent-wiki.md"],
      review_count: 0,
      model_calls: 2,
      input_tokens: 200,
      output_tokens: 100,
    });
  ask = vi
    .fn<(input: QueryInput) => Promise<QueryResult>>()
    .mockResolvedValue(queryResult());
  listPages = vi.fn<() => Promise<WikiPageSummary[]>>().mockResolvedValue([pageSummary]);
  getPage = vi.fn<(pageId: string) => Promise<WikiPage>>().mockResolvedValue(page);
  rebuildWiki = vi
    .fn<() => Promise<WikiPageSummary[]>>()
    .mockResolvedValue([pageSummary]);
}

describe("App", () => {
  it("loads sources and the generated wiki catalog", async () => {
    renderApp(new FakeWorkbenchService());

    expect(await screen.findByText("LLM Wiki Notes")).toBeInTheDocument();
    expect(await screen.findByText("Persistent Wiki")).toBeInTheDocument();
    expect(screen.getByText(/knowledge pattern · 1 nguồn/i)).toBeInTheDocument();
  });

  it("submits a grounded question and renders citations", async () => {
    const service = new FakeWorkbenchService();
    renderApp(service);
    await screen.findByText("LLM Wiki Notes");

    fireEvent.change(screen.getByPlaceholderText("Đặt câu hỏi..."), {
      target: { value: "What does a persistent wiki store?" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Gửi" }));

    expect(await screen.findByText(/stores maintained knowledge/i)).toBeInTheDocument();
    expect(screen.getByText(/page_1 · section: concept/i)).toBeInTheDocument();
    expect(service.ask).toHaveBeenCalledWith(
      expect.objectContaining({ question: "What does a persistent wiki store?" }),
    );
  });

  it("uploads and ingests a source through the Wiki Agent", async () => {
    const service = new FakeWorkbenchService();
    renderApp(service);
    await screen.findByText("LLM Wiki Notes");
    const file = new File(["# New"], "new.md", { type: "text/markdown" });

    fireEvent.change(screen.getByLabelText("Chọn tệp tài liệu"), {
      target: { files: [file] },
    });
    fireEvent.click(screen.getByRole("button", { name: "Tải lên" }));
    await waitFor(() => expect(service.uploadSource).toHaveBeenCalled());

    fireEvent.click(screen.getByRole("button", { name: "Wiki Agent" }));
    await waitFor(() => expect(service.ingestSource).toHaveBeenCalledWith("src_1"));
    expect(await screen.findByText(/1 trang thay đổi, 2 model calls/i)).toBeInTheDocument();
  });

  it("opens a wiki page and rebuilds the deterministic index", async () => {
    const service = new FakeWorkbenchService();
    renderApp(service);
    const pageButton = await screen.findByRole("button", { name: /Persistent Wiki/i });

    fireEvent.click(pageButton);
    expect(
      await screen.findByText(/Knowledge compounds across operations/i),
    ).toBeInTheDocument();
    expect(service.getPage).toHaveBeenCalledWith("page_1");

    fireEvent.click(screen.getByRole("button", { name: "Đồng bộ" }));
    await waitFor(() => expect(service.rebuildWiki).toHaveBeenCalled());
    expect(await screen.findByText("Wiki và SQLite đã đồng bộ.")).toBeInTheDocument();
  });

  it("uses selected sources as optional query scope", async () => {
    const service = new FakeWorkbenchService();
    renderApp(service);
    await screen.findByText("LLM Wiki Notes");

    fireEvent.click(screen.getByRole("checkbox", { name: "Query scope" }));
    fireEvent.change(screen.getByPlaceholderText("Đặt câu hỏi..."), {
      target: { value: "Tài liệu lưu trữ điều gì?" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Gửi" }));

    await waitFor(() =>
      expect(service.ask).toHaveBeenCalledWith(
        expect.objectContaining({
          question: "Tài liệu lưu trữ điều gì?",
          sourceIds: ["src_1"],
        }),
      ),
    );
  });
});

function renderApp(service: WorkbenchGateway) {
  return render(
    <WorkbenchProvider service={service}>
      <App />
    </WorkbenchProvider>,
  );
}

function queryResult(): QueryResult {
  return {
    query_id: "qry_1",
    question: "What does a persistent wiki store?",
    mode: "deep",
    answer: "A persistent wiki stores maintained knowledge before query time.",
    confidence: "high",
    citations: [
      {
        page_id: "page_1",
        source_id: "src_1",
        locator: "section: concept",
        quote_or_summary: "A persistent wiki accumulates knowledge.",
      },
    ],
    open_questions: [],
    pages_read: ["page_1"],
    sources_inspected: [],
    created_at: "2026-06-18T00:00:00Z",
  };
}
