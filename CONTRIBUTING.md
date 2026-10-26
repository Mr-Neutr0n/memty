# Contributing to NexorAI

Thanks for helping improve NexorAI. Contributions are welcome for the Next.js workspace, Express and MongoDB backend, model providers, portable SmartMemory package, and documentation.

## Before you start

- Check the open issues and pull requests for existing work.
- For a substantial change, open or comment on an issue first so the approach can be agreed on.
- Do not start work on an issue assigned to someone else without checking with the maintainers.
- Never post API keys, session secrets, database credentials, personal data, or populated environment files in an issue or pull request.

## Set up locally

1. Install Node.js 20.9 or later, npm, and MongoDB (or use a development MongoDB deployment).
2. Clone the repository and install dependencies:
   ```sh
   npm install
   cd backend && npm install
   ```
3. Copy `.env.example` to `.env` and `backend/.env.example` to `backend/.env`. Add only local development credentials. Keep these files private.
4. Start the backend and frontend in separate terminals:
   ```sh
   cd backend && npm run dev
   ```
   ```sh
   npm run dev
   ```
5. Open http://localhost:3001. Sign-in, memory, and database-backed features need the backend and MongoDB. Provider features also need the relevant provider credentials.

See the root README and the guides in `app/`, `backend/`, `providers/`, and `SmartMemory/` for component-specific details.

## Choose an issue and plan the change

- Issues marked **good first issue** are intended as smaller entry points, but please read the full acceptance criteria before starting.
- Comment on the issue to let maintainers know you are working on it. Describe your proposed solution for larger changes.
- Keep pull requests focused on one issue. If requirements are unclear, ask in the issue before implementing a large change.
- Do not broaden the scope or introduce new dependencies without explaining the need.

## Branches and commits

Create a branch from the current `main` branch. Use a short descriptive name, for example:

```text
fix/sidebar-mobile-overflow
feat/github-oauth
docs/provider-setup
```

Write clear commit messages that explain the change. Do not include unrelated formatting or generated files.

## Implementation expectations

- Follow the existing structure and conventions in the part of the project you change.
- Keep secrets on the server. Never expose provider credentials, session signing keys, or database credentials to browser code.
- Preserve existing authentication, conversation ownership, and memory privacy boundaries.
- Handle loading, empty, success, and error states in user-facing flows.
- Make keyboard use, visible focus, responsive layouts, and accessible names part of UI changes.
- Update relevant documentation and configuration examples when behavior or setup changes.
- Avoid committing build output, local databases, logs, real user data, or populated `.env` files.

## Verify your change

Run the checks relevant to your change before opening a pull request. At minimum, use the repository's available type/build checks when practical:

```sh
npm run typecheck
npm run build
```

For backend changes, run the backend checks or exercise the affected endpoint locally. For SmartMemory changes, follow its README and run the applicable Python checks. If a check cannot be run, say which one and why in the pull request.

## Open a pull request

- Push your branch and open a pull request targeting `main`.
- Link the issue using `Closes #<issue-number>` when the PR fully resolves it, or `Refs #<issue-number>` when it is related but does not close it.
- Explain the problem, the implementation, and any user-visible behavior changes.
- List the checks you ran and their results.
- Add screenshots or a short recording for visual changes, including relevant mobile behavior.
- Call out configuration changes, migration steps, provider requirements, or known limitations.
- Keep the PR focused and respond to review feedback with follow-up commits.

Maintainers review contributions and decide whether and when to merge them. Opening a pull request does not guarantee acceptance; please do not merge your own contribution unless a maintainer has explicitly authorized it.
