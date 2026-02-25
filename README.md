# Sprout MCP

**Drop your Opus bill 80%.** Model-tiered content pipeline for MCP — cheap models seed work, expensive models verify it.

Sprout routes tasks to the right model tier automatically. Haiku drafts, Sonnet fact-checks, Opus verifies. Every chunk tracks provenance, confidence, and cost.

## Install

```bash
uvx sprout-mcp
```

Or add to Claude Code's MCP config (`~/.claude/settings.json`):

```json
{
  "mcpServers": {
    "sprout": {
      "command": "uvx",
      "args": ["sprout-mcp"]
    }
  }
}
```

## How It Works

```
  Haiku (seed)  →  Sonnet (watered)  →  Opus (sprouted)
    Draft            Fact-check           Verify
    $0.005/M         $0.015/M             $0.075/M
```

1. **Seed** — Haiku drafts content cheaply (summarization, extraction, first passes)
2. **Water** — Sonnet reviews and fact-checks the seeds
3. **Sprout** — Opus deep-verifies only what passed Sonnet's review

Instead of running everything through Opus at $75/M output tokens, most work stays at Haiku's $5/M. Only the final verification — typically 10-20% of total work — touches Opus.

## Tools (13)

| Tool | Description |
|------|-------------|
| `submit_chunk` | Store content with provenance (model, task type, sources) |
| `get_review_queue` | List chunks needing review, filtered by confidence/project |
| `mark_reviewed` | Promote (seed→watered→sprouted) or reject chunks |
| `recommend_model` | Get model recommendation for a task type |
| `get_stats` | Dashboard of chunk counts, confidence levels, token usage |
| `export_chunks` | Export verified chunks as JSON |
| `opus_test` | Generate structured review summary for batch verification |
| `schedule_task` | Schedule tasks to run at a specific time or delay |
| `list_scheduled` | View pending scheduled tasks |
| `cancel_scheduled` | Cancel a pending scheduled task |
| `configure_routing` | Add/update routing rules at runtime |
| `get_cost_report` | Estimated spend per model with real pricing |
| `retry_on_error` | Track failed attempts with backoff guidance |

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SPROUT_DB_PATH` | `~/.sprout/sprout.db` | SQLite database location |
| `SPROUT_CONFIG` | *(none)* | Path to JSON config file for custom routes and pricing |
| `SPROUT_MAX_RETRIES` | `3` | Max retry attempts before giving up |
| `SPROUT_RETRY_BACKOFF` | `2.0` | Exponential backoff base (seconds) |

### Custom Config File

Create a JSON file and point `SPROUT_CONFIG` at it:

```json
{
  "routes": {
    "code_review": { "tier": "sonnet", "reason": "Code analysis needs reasoning" },
    "translation": { "tier": "haiku", "reason": "Straightforward language task" }
  },
  "pricing": {
    "custom-model": 10.00
  }
}
```

### Default Routing Table

| Task Type | Tier | Why |
|-----------|------|-----|
| `biography_synthesis` | haiku | Factual summarization |
| `council_description` | haiku | Historical summarization |
| `document_synopsis` | haiku | Content summarization |
| `json_validation` | haiku | Structural verification |
| `summarization` | haiku | General summarization |
| `data_extraction` | haiku | Structured extraction |
| `fact_check_first_pass` | sonnet | Cross-reference claims |
| `code_review` | sonnet | Code analysis |
| `fact_check_final` | opus | Deep factual verification |
| `theological_analysis` | opus | Domain expertise required |
| `complex_analysis` | opus | Deep reasoning required |

Unknown task types default to haiku — start cheap, escalate if needed.

## Example Workflow

```
You: Use recommend_model for "biography_synthesis"
Sprout: biography_synthesis → haiku-4.5 (Factual summarization)

You: Use submit_chunk to store the Haiku output
Sprout: Stored chunk abc12345 [seed] for person-001.biography

You: Use get_review_queue to see what needs fact-checking
Sprout: 1 chunk pending review

You: Use mark_reviewed to promote after Sonnet fact-checks it
Sprout: Chunk abc12345 → watered (verified by sonnet-4.6)

You: Use get_cost_report
Sprout: haiku-4.5: ~1,300 tokens (1 chunk) — $0.0065
        Total: $0.0065
```

## Development

```bash
git clone https://github.com/mepsopti/sprout-mcp.git
cd sprout-mcp
uv sync --extra dev
uv run pytest
```

## Support

If Sprout saves you money on your AI bill, consider buying me a coffee:

[![Buy Me A Coffee](https://img.shields.io/badge/Buy%20Me%20A%20Coffee-support-yellow?style=flat&logo=buy-me-a-coffee)](https://buymeacoffee.com/mepsopti)

## License

MIT
