# Architecture Documentation for Claude Code: Best Practices

> Research date: 2026-03-28
> Sources: Anthropic official docs, HumanLayer blog, awesome-claude-md, awesome-claude-skills

## Key Findings

### 1. CLAUDE.md = navigation map, not encyclopedia

Anthropic prohibits "file-by-file descriptions" and "detailed API docs" in CLAUDE.md.
Use `@docs/architecture.md` imports for on-demand loading. Prefer pointers to copies.
"Don't include code snippets — they become out-of-date. Use `file:line` references."

**Sources**: [Anthropic Best Practices](https://code.claude.com/docs/en/best-practices), [HumanLayer Blog](https://www.humanlayer.dev/blog/writing-a-good-claude-md)

### 2. Size matters: ~200 lines max, beyond that rules get ignored

"Bloated CLAUDE.md files cause Claude to ignore your actual instructions."
For each line: "Would removing this cause Claude to make mistakes? If not, cut it."

**Sources**: Anthropic Best Practices, HumanLayer Blog

### 3. Tables for quick-ref, prose for architecture decisions, @-links for specs

Tables: tech stack, module mapping, comparisons.
Prose: architectural explanations, decision rationale ("Why before How").
File references: `src/agents/base.py -> docs/02-agents-core.md` for targeted context loading.

**Source**: awesome-claude-md analysis

### 4. Skills for domain knowledge that shouldn't load every session

"CLAUDE.md is loaded every session, so only include things that apply broadly.
For domain knowledge or workflows that are only relevant sometimes, use Skills."

**Source**: Anthropic Best Practices

## Actionable Recommendations

1. Keep CLAUDE.md under 200 lines (currently ~87 lines -- good)
2. Architecture details in `docs/architecture.md`, linked from CLAUDE.md (DONE)
3. Remove rules Claude follows by default (async I/O, type hints) -- keep only project-specific
4. Consider Skills for persona prompts and eval workflows
