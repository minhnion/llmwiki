# CLAUDE.md

Follow `AGENTS.md` as the repository authority.

This project is a general-purpose Wiki Agent, not a traditional chunk-RAG
system and not a multi-stage knowledge compiler.

The key rule is:

> LLM/VLM decides semantic meaning; deterministic code provides safe tools,
> provenance, persistence, validation, budgets, and search execution.

Before changing architecture, read:

- `docs/llm-wiki.md`
- `docs/guide_llm_wiki_nashu.md`
- `docs/wiki-agent-architecture.md`
- `docs/roadmap.md`
- `docs/evaluation.md`

Do not add domain mappings, semantic regexes, keyword routers, fixed
taxonomies, mandatory raw chunk retrieval, or new compiler/auditor stages.

The normal product loop is:

```text
source + current wiki
  -> Wiki Agent understands
  -> Wiki Agent creates/updates pages
  -> deterministic validation and commit
  -> query/lint agents continue improving the same wiki
```

Markdown is the primary semantic artifact. SQLite indexes it and stores
operational/provenance state.
