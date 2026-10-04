# `web`

Browser simulator. `server.py` serves `index.html` at `/` and these files under `/static`.

| File | What it is for |
| --- | --- |
| `index.html` | Page layout: schedule rail, talk panel, and today’s board. The schedule form adds a dose with the mouse. The talk box is the voice path. |
| `app.js` | Page behavior. Sends each utterance to `POST /api/talk`, refreshes the board from `GET /api/today`, and adds or removes doses through `/api/schedules`. The Mic button uses the browser speech API, keeps listening through short pauses, and sends the phrase after about 1.2 seconds of silence. Suggested phrases are the chips above the transcript. “Speak replies” reads the answer aloud and is cancelled while the mic is open. |
| `styles.css` | Layout and colors for the three panels. |

Voice examples the page suggests:

- “Register him as Raj”
- “Raj needs to take medicine at 8 AM and 8 PM”
- “What's due now?”
- “Switch to caregiver mode”

The script tag in `index.html` includes a `?v=` query so a refresh picks up a new `app.js` after that number changes.
