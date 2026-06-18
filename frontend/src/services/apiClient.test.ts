import { describe, expect, it, vi } from "vitest";

import { ApiClient, ApiError } from "./apiClient";

describe("ApiClient", () => {
  it("sends query fields using the backend contract", async () => {
    const fetcher = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ query_id: "qry_1" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    const client = new ApiClient({
      baseUrl: "http://localhost:8020/api/",
      fetcher,
    });

    await client.ask({
      question: "What is LLM Wiki?",
      mode: "deep",
      sourceIds: ["src_1"],
      maxEvidence: 6,
    });

    expect(fetcher).toHaveBeenCalledWith(
      "http://localhost:8020/api/query",
      expect.objectContaining({ method: "POST" }),
    );
    const request = fetcher.mock.calls[0][1] as RequestInit;
    expect(JSON.parse(request.body as string)).toEqual({
      question: "What is LLM Wiki?",
      mode: "deep",
      source_ids: ["src_1"],
      tags: [],
      max_candidates: 24,
      max_evidence: 6,
    });
  });

  it("uploads files as multipart form data", async () => {
    const fetcher = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ id: "src_1" }), {
        status: 201,
        headers: { "Content-Type": "application/json" },
      }),
    );
    const client = new ApiClient({ baseUrl: "/api", fetcher });
    const file = new File(["# Notes"], "notes.md", { type: "text/markdown" });

    await client.uploadSource({
      file,
      title: "Notes",
      sourceType: "markdown",
      tags: ["test"],
    });

    const request = fetcher.mock.calls[0][1] as RequestInit;
    expect(request.body).toBeInstanceOf(FormData);
    const form = request.body as FormData;
    expect(form.get("file")).toBe(file);
    expect(form.get("title")).toBe("Notes");
    expect(form.get("source_type")).toBe("markdown");
    expect(form.getAll("tags")).toEqual(["test"]);
  });

  it("raises ApiError with backend detail", async () => {
    const client = new ApiClient({
      baseUrl: "/api",
      fetcher: vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail: "Source not found" }), {
          status: 404,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    });

    await expect(client.ingestSource("missing")).rejects.toEqual(
      new ApiError(404, "Source not found"),
    );
  });
});
