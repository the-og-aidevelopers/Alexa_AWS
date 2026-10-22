# `frontend`

React (Vite) UI for Pillow. Three screens in one app, chosen by URL:

| URL | Screen |
| --- | --- |
| `/` | Dashboard: household panel, talk panel, and today's board. Adding a person, a person's medicines, and the medicine form are modal dialogs. |
| `/agent` | The tap-to-talk circle with a live caption and transcript. |
| `/login` | Local caregiver sign in and household creation. |

## Layout

- `src/pages/` — `Dashboard.jsx`, `Agent.jsx`, `Login.jsx`.
- `src/components/` — panels, dialogs (`Modal` wraps the native `<dialog>`), and the `Orb` canvas.
- `src/hooks/` — `useVoice` (the microphone), `useMeter` (level meter for the orb), `useSession`.
- `src/api.js` — every call to the Python server (`/api/talk`, `/api/today`, `/api/people`, `/api/schedules`, `/api/transcribe` is called by the recorder).
- `public/listener.js`, `public/recorder.js` — the speech input, loaded as plain scripts. `AutoListener` records a phrase and sends it to `/api/transcribe` (local Whisper or ElevenLabs Scribe v2, whichever the server reports), and falls back to the browser's own speech engine. Their tests are `tests/listener.test.cjs` and `tests/recorder.test.cjs`.
- `src/styles/` — plain CSS, one file per screen. The build merges them, so page styles are scoped under `.agent-page` and `.login-page`.

## Commands

```bash
npm install
npm run build   # writes ../web/dist, which the Python server serves
npm test        # component tests with Vitest and Testing Library
npm run dev     # Vite dev server on :5173, proxying /api and /mcp to 127.0.0.1:8010
```

For `npm run dev`, start the Python server on port 8010 and sign in at `http://localhost:5173/login`.
