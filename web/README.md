# `web`

The browser UI is a React app that lives in [`frontend/`](../frontend/README.md). `npm run build` there writes the compiled app to `web/dist`, which is git-ignored.

`server.py` serves `web/dist/index.html` for `/`, `/agent` and `/login` (the app picks the screen from the URL) and everything else in `web/dist` under `/static`. If the app has not been built, those pages return a short message saying how to build it.

Build it once before starting the server:

```bash
cd frontend
npm install
npm run build
```
