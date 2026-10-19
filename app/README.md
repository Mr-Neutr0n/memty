# Frontend guide

This folder contains the NexorAI Next.js App Router UI, API routes, shared global styles, and route-level pages. Start the frontend from the repository root with `npm run dev`; it serves on port 3001 by default.

## Pages

| Route | Source | Purpose |
| --- | --- | --- |
| `/` | `page.tsx` + `components/legacy-page.tsx` | Landing page and model overview |
| `/login` | `login/page.tsx` | Sign in, register, and optional Google sign-in UI |
| `/chatbot` | `chatbot/page.tsx` | Multi-model chat workspace |
| `/memory` | `memory/page.tsx` + `memory/memory-dashboard.tsx` | Memory controls, conversation summaries, and usage |
| `/terms` | `terms/page.tsx` | Terms of Service draft |
| `/privacy` | `privacy/page.tsx` | Privacy Notice draft |
| `/api-reference` | `api-reference/page.tsx` | First-party chat API behavior and limitations |

Landing, login, and chat pages render legacy HTML strings from `lib/legacy-markup.ts`; `LegacyPage` attaches their browser scripts from `public/legacy/`. The Memory dashboard and legal pages use React components directly.

## API routes

- `POST /api/chat`: authenticates through the backend, retrieves user context, calls the selected model, optionally compares a second model, and persists the turn.
- `GET /api/config`: lists configured models and public metadata. It does not return provider secrets.
- `/api/users/*` and `/users/*`: Next proxy routes to the backend user service.
- `/backend/*`: generic backend proxy used by the app.
- `GET /health`: frontend health response.
- `POST /api/clear-history`: clears browser history through the app's local-history flow.

The chat handler limits request bodies to 100 KiB and messages to 30,000 characters. Its current 30 requests per minute limit is in-memory per frontend process. It requires the HTTP-only session cookie from the backend. Chat generation currently returns a complete response rather than a token stream.

## Responsive layout

`globals.css` contains the shared legal and memory styles plus scoped legacy landing, login, and chat styles. Keep styles scoped under `.legacy-page-landing`, `.legacy-page-login`, or `.legacy-page-chat` to avoid affecting unrelated routes. The mobile chat sidebar becomes a drawer; the message composer wraps for narrow screens and accounts for device safe areas; compare results stack vertically on phones. Landing feature cards use two columns on tablets and one on narrow phones. Memory cards, usage rows, legal content, dialogs, and navigation reflow at phone widths.

The root layout declares a device-width viewport with `viewportFit: cover`. Interactive controls should retain touch-friendly dimensions, and long text should wrap instead of widening the viewport.

## Frontend environment

See the root `.env.example` for provider keys, model names, output limits, proxy target, frontend port, Google client ID, and memory defaults. Provider keys stay server-side in Next.js routes and must not be exposed through client JavaScript.

The workspace's short recent-history list and theme/display preferences use browser storage. Full neutral conversation context and portable memory are stored in MongoDB through the backend. Deleting browser storage removes local UI state; use the Memory page to delete saved server conversations and memories.
