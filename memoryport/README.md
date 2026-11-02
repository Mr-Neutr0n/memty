# Memty SDK compatibility modules

The public product, package, Python import path, and primary CLI are **Memty**. Install the `memty` distribution and use `from memty import ...`; model routing, provider adapters, portable memory, the temporal vault, and the atomic context compiler are available through that namespace.

```shell
python -m pip install memty
memty --help
memty models
memty chat --interactive
```

```python
from memty import Memty, ModelConfig, load_client

assistant = load_client()  # reads ~/.memty/models.json
answer = assistant.chat("Summarize this question")
print(answer.text)
```

This directory contains implementation modules retained so existing integrations and stored vaults continue to work during migration. New applications should import from `memty`, use the `memty` CLI, and configure `MEMTY_*` environment variables. Existing `MEMTY_*` / `MEMTY_VAULT_*` settings and older data folders are still recognized as fallbacks.

See the [Memty guide](../memty/README.md), [project overview](../README.md), and [GitHub Pages site](../GitPage/index.html) for installation, CLI, SDK, memory, routing, and deployment details.