# Token Burn Benchmark

This benchmark makes a five-turn synthetic architecture handoff reproducible. It does **not** establish that Memty saves 85–95% against real RAG or MCP products, or that it preserves 100% of context across assistants. Those claims require additional measurements.

## Live Claude and Gemini results

Three live runs used `claude-haiku-5-5` and `gemini-2.5-flash`, alternating across five turns for each mode. Each turn supplied the selected context, the current question, and prior questions and model answers. The input and output counts below are reported by the providers; the exact-answer score checks two expected values per turn in the model's response.

| Run | Context supplied | Input tokens | Output tokens | Exact answers |
| ---: | --- | ---: | ---: | ---: |
| 1 | Full document replay | 4,663 | 309 | 9/10 |
| 1 | Simulated retrieval | 3,148 | 463 | 9/10 |
| 1 | Selected Memty context | 1,816 | 204 | 10/10 |
| 2 | Full document replay | 4,663 | 308 | 9/10 |
| 2 | Simulated retrieval | 3,090 | 477 | 9/10 |
| 2 | Selected Memty context | 1,816 | 204 | 10/10 |
| 3 | Full document replay | 4,663 | 281 | 9/10 |
| 3 | Simulated retrieval | 3,148 | 363 | 9/10 |
| 3 | Selected Memty context | 1,816 | 204 | 10/10 |

Across the three runs, Memty used 5,448 input tokens versus 13,989 for full replay (61.1% less) and 9,386 for simulated retrieval (42.0% less). It returned 30/30 expected values exactly, compared with 27/30 for each baseline. [Run 1](results/claude-gemini-run1.json), [run 2](results/claude-gemini-run2.json), and [run 3](results/claude-gemini-run3.json) contain the per-turn model answers and usage.

All runs use the **same synthetic fixture** and manually prepared facts. The retrieval baseline is curated snippets and illustrative schemas in the prompt, not a real RAG or MCP system or tool call. The benchmark does not measure the cost or accuracy of creating Memty facts, and its three repeats do not prove general performance, universal continuity, or accuracy on other tasks. The full conversation history can differ between modes when the assistants produce different answers.

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

The runner can make 15 **billable** API requests: five alternating between Claude and either Perplexity or Gemini for each of the three payloads. It replays prior questions and answers across providers, records provider-reported input and output usage, and checks exact values in the model's JSON response. It does not execute real MCP tools: the retrieval baseline contains illustrative schemas and curated snippets as text.

Set `ANTHROPIC_API_KEY` and `PERPLEXITY_API_KEY` in your environment, then provide currently supported model identifiers:

```sh
python -m benchmarks.token_burn.run --live --anthropic-model CLAUDE_MODEL_ID --perplexity-model PROVIDER/MODEL_ID --output live-results.json
```

Model availability and billing are controlled by each provider. See [Anthropic's token-counting documentation](https://platform.claude.com/docs/en/build-with-claude/token-counting) and the [Perplexity Agent API](https://docs.perplexity.ai/api-reference/agent-post). Review generated responses before publishing results. A real product comparison still needs named RAG/MCP implementations, actual tool calls and roundtrip timings, multiple representative tasks and trials, and a clear accounting of setup and memory-creation costs.

Alternatively, set `ANTHROPIC_API_KEY` and `GEMINI_API_KEY` and alternate Claude with Gemini:

```sh
python -m benchmarks.token_burn.run --live --second-provider gemini --anthropic-model claude-haiku-5-5 --gemini-model gemini-2.5-flash --output live-results.json
```

The fixture digest identifies the original fixture; the `providers` field records the Gemini substitution. Gemini output usage is total tokens minus input tokens, including any reported thinking tokens. The runner requests a zero thinking budget for Gemini 2.5 Flash. These live calls require working provider access and may be billable.
