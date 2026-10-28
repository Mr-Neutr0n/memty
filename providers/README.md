# Model provider and routing guide

Each model adapter in this directory accepts normalized messages and returns a normalized reply and provider usage where available. The rest of the app calls `providers/index.js`, so model selection, fallback, usage normalization, and cost estimation use a shared path.

> **Provider path:** the chat route passes neutral messages to the shared provider layer; the selected adapter handles provider-specific request details. Secrets remain in server-side environment variables. The root [README](../README.md) shows where providers fit in the full application.

| If you are changing... | Start with... |
| --- | --- |
| Prompt orchestration or saved chat turns | [`app/api/chat/route.ts`](../app/api/chat/route.ts) |
| Model IDs, configuration lookup, or fallback order | [`registry.js`](registry.js) and [`index.js`](index.js) |
| Provider request format | The adapter module for that provider, such as [`gemini.js`](gemini.js) |
| User memory injected into prompts | [Memory guide](../app/memory/README.md) |

## How a provider call moves through this folder

```text
chat route → providers/index.js → providers/registry.js → provider adapter → external API
                   └─ normalize reply, usage, and fallback metadata ─┘
```

## Registered models

| App model ID | Provider | Environment key |
| --- | --- | --- |
| `gemini-flash` | Google Gemini | `GEMINI_API_KEY` |
| `claude-haiku` | Anthropic Claude | `CLAUDE_API_KEY` |
| `grok-ai` | xAI Grok | `GROK_API_KEY` |
| `kimi` | Moonshot AI Kimi | `KIMI_API_KEY` |
| `chatgpt` | OpenAI-compatible model via OpenRouter | `OPEN_ROUTER_OPEN_API_KEYS` |
| `nemotron` | NVIDIA via OpenRouter | `OPEN_ROUTER_API_KEY` |
| `llama` | Meta via OpenRouter | `OPEN_ROUTER_API_KEY` |

The model name and metadata defaults are in `registry.js`; `GET /api/config` reports whether each model's credential is configured without returning the key. Provider access, model IDs, rates, and availability can change independently of this application.

## Adapter interface

Adapters expose `chat({ messages, memory, stream, modelId })`. Messages use neutral `system`, `user`, and `assistant` roles. The adapter returns at least a reply and may return raw provider usage. `providers/index.js` normalizes prompt/completion token fields and attaches the selected model and fallback status.

Files:

- `index.js`: model selection, Auto heuristics, fallback chain, usage normalization, and optional cost estimate.
- `registry.js`: model IDs, display metadata, configured-key lookup, and operator-set rates.
- `gemini.js`, `claude.js`, `grok.js`, `kimi.js`, `openai.js`, `nvidia.js`, `llama.js`: model-specific request adapters.
- `openai-compatible.js`: shared OpenAI-compatible HTTP request behavior.
- `conversation.js`: shared provider conversation formatting utilities.

## Routing behavior

Auto routes by task signals: deep reasoning, long context, code/debug, structured output, memory-backed synthesis, and general chat. It prefers configured providers in each task class, then uses the registry's ordered fallback list if a request fails. Compare mode makes a separate call to the requested second model without fallback. The optional Python package in `memoryport/` adds a capability-constrained LinUCB learner and portable JSON memory store for Python integrations; it is not required to run the Next.js app.

This is heuristic routing, not a quality benchmark or guaranteed best-model selection. If no requested/fallback provider is configured, the chat API returns an error. Responses are currently non-streaming. The registry lists capability metadata; it should not be read as a guarantee that the present UI forwards every modality (for example, vision) to each provider.

## Cost estimates

For an estimate, set both rate variables for a model ID, in USD per million input/output tokens. Example for Gemini:

```env
NEXOR_GEMINI_FLASH_INPUT_USD_PER_MILLION=0.1
NEXOR_GEMINI_FLASH_OUTPUT_USD_PER_MILLION=0.4
```

Estimates are based on provider-reported token counts where available and operator-entered rates. They do not charge users and are not a billing ledger. Keep rates current with provider pricing.

## Adding a provider

1. Add its ID, provider label, configured key, context metadata, and fallback IDs to `registry.js`.
2. Implement the normalized `chat` adapter in a new module. Keep credentials in environment variables and set a request timeout.
3. Register the adapter in `index.js`; include usage-field normalization if the provider reports different fields.
4. Update model selection UI/registry data and `GET /api/config` expectations as needed.
5. Update the root README and this guide. Do not claim a provider capability that the chat request path does not support.

