# Token Burn Benchmark

This benchmark makes a five-turn synthetic architecture handoff reproducible. It does **not** establish that Memty saves 85–95% against real RAG or MCP products, or that it preserves 100% of context across assistants. Those claims require additional measurements.

## Offline results

The checked-in [results](offline_results.json) estimate the memory payload supplied over five turns, using Memty's heuristic token estimator, not a provider tokenizer:

| Memory supplied each turn | Estimated tokens, five turns | Reduction vs. this baseline |
| --- | ---: | ---: |
| Full synthetic source documents | 3,710 | 88.0% |
| Ten curated snippets and illustrative tool definitions | 1,620 | 72.5% |
| One selected Memty context | 445 | — |

All ten expected values were present in the supplied context across the five questions in each mode. This checks the inputs, **not whether an assistant recalled or understood them**. The snippets are selected with knowledge of the answers, and the reviewed Memty facts are preloaded from the fixture. Extraction, review, initial memory creation, questions, conversation history, outputs, billing, latency, and actual tool calls are excluded from these offline estimates. This is one synthetic fixture, not a comparison with a deployed graph or vector product.

Reproduce from the repository root:

```sh
python -m benchmarks.token_burn.run --output benchmarks/token_burn/offline_results.json
```

The [fixture](architecture.json) contains ten synthetic facts and five questions; the result includes its SHA-256 digest. The Memty payload comes from the same ledger context selection used by the browser bridge. These counts are not the proposed 14,200 / 4,800 / 310 numbers; those numbers have not been verified here.

## Optional live API measurement

The runner can make 15 **billable** API requests: five alternating between Claude and Perplexity for each of the three payloads. It replays prior questions and answers across providers, records provider-reported input and output usage, and checks exact values in the model's JSON response. It does not execute real MCP tools: the retrieval baseline contains illustrative schemas and curated snippets as text. No live results are included because provider credentials were unavailable.

Set `ANTHROPIC_API_KEY` and `PERPLEXITY_API_KEY` in your environment, then provide currently supported model identifiers:

```sh
python -m benchmarks.token_burn.run --live --anthropic-model CLAUDE_MODEL_ID --perplexity-model PROVIDER/MODEL_ID --output live-results.json
```

Model availability and billing are controlled by each provider. See [Anthropic's token-counting documentation](https://platform.claude.com/docs/en/build-with-claude/token-counting) and the [Perplexity Agent API](https://docs.perplexity.ai/api-reference/agent-post). Review generated responses before publishing results. A real product comparison still needs named RAG/MCP implementations, actual tool calls and roundtrip timings, multiple representative tasks and trials, and a clear accounting of setup and memory-creation costs.
