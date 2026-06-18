import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import App from "./App";
import type {
  Contradiction,
  GraphEntityDetail,
  GraphVisualization,
  QueryResult,
  SourceIngestResult,
  SourceRef,
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
};

const graph: GraphVisualization = {
  nodes: [
    { id: "ent_1", label: "LLM Wiki", node_type: "entity", confidence: 0.9 },
    { id: "literal_1", label: "Knowledge artifacts", node_type: "text", confidence: 0.8 },
  ],
  edges: [
    {
      id: "rel_1",
      source: "ent_1",
      target: "literal_1",
      label: "persists",
      confidence: 0.9,
      claim_id: "cl_1",
      evidence_id: "ev_1",
    },
  ],
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
      page_path: "/wiki/source.md",
      evidence_count: 2,
      claim_count: 2,
      entity_count: 1,
      review_item_count: 0,
      compiler_run_id: "crun_1",
      pass_count: 1,
      artifact_count: 2,
      coverage_status: "complete",
      graph_run_id: "grun_1",
      relation_count: 1,
      contradiction_count: 0,
    });
  buildGraph = vi.fn().mockResolvedValue({
    graph_run_id: "grun_1",
    source_ids: [],
    claim_count: 2,
    relation_count: 1,
    contradiction_count: 0,
    merge_candidate_count: 0,
    entity_page_count: 1,
    status: "completed",
    started_at: "2026-06-18T00:00:00Z",
    finished_at: "2026-06-18T00:00:01Z",
  });
  ask = vi
    .fn<(input: QueryInput) => Promise<QueryResult>>()
    .mockResolvedValue(queryResult());
  graph = vi.fn<(query: string) => Promise<GraphVisualization>>().mockResolvedValue(graph);
  entity = vi
    .fn<(entityIdOrName: string) => Promise<GraphEntityDetail>>()
    .mockRejectedValue(new Error("Not used"));
  contradictions = vi
    .fn<() => Promise<Contradiction[]>>()
    .mockResolvedValue([]);
}

describe("App", () => {
  it("loads sources, graph, and contradictions", async () => {
    renderApp(new FakeWorkbenchService());

    expect(await screen.findByText("LLM Wiki Notes")).toBeInTheDocument();
    expect(screen.getByText("2 nút")).toBeInTheDocument();
    expect(screen.getByText("Không có mâu thuẫn đang mở.")).toBeInTheDocument();
  });

  it("submits a grounded chat question and renders citations", async () => {
    const service = new FakeWorkbenchService();
    renderApp(service);
    await screen.findByText("LLM Wiki Notes");

    fireEvent.change(screen.getByPlaceholderText("Đặt câu hỏi cho LLM Wiki..."), {
      target: { value: "What does LLM Wiki persist?" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Hỏi" }));

    expect(await screen.findByText(/persists source-grounded artifacts/i)).toBeInTheDocument();
    expect(screen.getAllByText("section: concept", { exact: false })).toHaveLength(2);
    expect(service.ask).toHaveBeenCalledWith(
      expect.objectContaining({ question: "What does LLM Wiki persist?" }),
    );
  });

  it("uploads a selected file", async () => {
    const service = new FakeWorkbenchService();
    renderApp(service);
    await screen.findByText("LLM Wiki Notes");
    const file = new File(["# New"], "new.md", { type: "text/markdown" });

    fireEvent.change(screen.getByLabelText("Chọn tệp tài liệu"), {
      target: { files: [file] },
    });
    fireEvent.click(screen.getByRole("button", { name: "Tải lên" }));

    await waitFor(() => expect(service.uploadSource).toHaveBeenCalled());
    expect(service.uploadSource.mock.calls[0][0].file).toBe(file);
  });

  it("runs source ingest and graph build from the workbench", async () => {
    const service = new FakeWorkbenchService();
    renderApp(service);
    await screen.findByText("LLM Wiki Notes");

    fireEvent.click(screen.getByRole("button", { name: "Ingest" }));

    await waitFor(() => expect(service.ingestSource).toHaveBeenCalledWith("src_1"));
    expect(
      await screen.findByText(/2 artifact, coverage complete, 1 quan hệ graph/i),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Dựng lại graph" }));

    await waitFor(() => expect(service.buildGraph).toHaveBeenCalledWith([]));
    expect(await screen.findByText(/Đã dựng graph: 1 quan hệ/i)).toBeInTheDocument();
  });

  it("uses selected ingested sources as query scope", async () => {
    const service = new FakeWorkbenchService();
    renderApp(service);
    await screen.findByText("LLM Wiki Notes");

    fireEvent.click(screen.getByRole("checkbox", { name: "Dùng trong phạm vi" }));
    fireEvent.change(screen.getByPlaceholderText("Đặt câu hỏi cho LLM Wiki..."), {
      target: { value: "Tài liệu lưu trữ điều gì?" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Hỏi" }));

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
    question: "What does LLM Wiki persist?",
    mode: "deep",
    answer: "LLM Wiki persists source-grounded artifacts.",
    confidence: "high",
    citations: [
      {
        evidence_id: "ev_1",
        source_id: "src_1",
        source_title: "LLM Wiki Notes",
        locator: "section: concept",
        quote_or_summary: "Defines persistence.",
        claim_ids: ["cl_1"],
      },
    ],
    used_claim_ids: ["cl_1"],
    matched_entities: ["LLM Wiki"],
    contradictions: [],
    open_questions: [],
    follow_up_questions: [],
    selected_evidence: [
      {
        evidence_id: "ev_1",
        source_id: "src_1",
        source_title: "LLM Wiki Notes",
        source_path: "/tmp/notes.md",
        wiki_page_path: "/wiki/notes.md",
        locator: "section: concept",
        modality: "text",
        text: "LLM Wiki persists artifacts.",
        summary: "Defines persistence.",
        confidence: 0.9,
        claim_ids: ["cl_1"],
        claims: ["LLM Wiki persists artifacts."],
        entities: ["LLM Wiki"],
        retrieval_score: 4,
        retrieval_channels: ["graph", "claim"],
      },
    ],
    candidate_count: 2,
    created_at: "2026-06-18T00:00:00Z",
    plan: {
      rewritten_question: "What does LLM Wiki persist?",
      intent: "fact",
      answer_language: "English",
      retrieval_strategy: "deep",
      keywords: ["LLM Wiki"],
      entity_hints: ["LLM Wiki"],
      subquestions: [],
      must_have_evidence: [],
      source_filters: [],
      time_filters: [],
    },
  };
}
