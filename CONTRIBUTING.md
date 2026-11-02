# Contributing to Memty

Thanks for helping improve Memty. The project has a Next.js app, an Express/MongoDB service, provider adapters, and an optional Python memory package. A focused change with a clear reproduction or outcome is easiest to review.

## Find the right area

| Change | Guide |
| --- | --- |
| Pages, chat UI, API routes, responsive behavior | [Frontend guide](app/README.md) |
| Authentication, sessions, REST endpoints, persistence | [Backend guide](backend/README.md) |
| Provider adapters, model registry, fallbacks | [Provider guide](providers/README.md) |
| Memory retrieval and dashboard behavior | [Memory guide](app/memory/README.md) |
| Python vault, CLI, MCP, or SmartRouter | [Memty guide](memty/README.md) |

## Before you start

1. Search existing [issues](https://github.com/RohanNK86/memty/issues) and pull requests to avoid duplicating work.
2. For a bug, include the route or command, steps to reproduce, expected result, actual result, and relevant sanitized logs.
3. For a feature, describe the user problem and a concrete acceptance outcome before expanding its scope.
4. For changes that affect account data or provider requests, explain which service owns the data and how user/account boundaries are preserved.

## Local setup

Follow the root [README setup](README.md#get-started) for the frontend and backend. The Python package and its optional extras have separate instructions in [Memty](memty/README.md#manual-install). You only need the services involved in your change; provider keys are optional unless the behavior depends on a live provider.

## Pull request checklist

- Keep the change focused and explain the user-visible result in the PR description.
- Update the relevant guide when a route, setting, supported flow, or limitation changes.
- Include before/after screenshots for visible UI changes and mention tested viewport sizes.
- Run the checks relevant to the files you changed; list the commands and results in the PR.
- Do not commit `.env` files, API keys, session secrets, personal data, or real user conversations.
- Call out migration, configuration, compatibility, or security implications.

## Documentation and issue reports

Use relative links for files inside the repository. Keep examples runnable and use placeholders for secrets. When reporting a problem, never attach credentials, session cookies, full private prompts, or user memory contents; reduce logs to the smallest sanitized excerpt that demonstrates the failure.

