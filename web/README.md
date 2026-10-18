# `web`

Browser simulator. `server.py` serves `index.html` at `/` and these files under `/static`.

| File | What it is for |
| --- | --- |
| `login.html`, `login.js` | Local caregiver registration/sign-in form. New accounts start with an empty private household. |
| `session.js` | Displays the household and handles sign out on both authenticated pages. |
| `index.html` | Page layout: household panel, talk panel, and today’s board, all fitting one screen. Adding a person, a person’s medicines, and the medicine form are modal dialogs. The talk box is the voice path. |
| `app.js` | Page behavior. Sends each utterance to `POST /api/talk`, refreshes the board from `GET /api/today`, and manages people and doses through `/api/people` and `/api/schedules`. Clearing today’s log is a chat command (“clear today’s log”). Suggested phrases are the chips above the transcript. “Speak replies” reads the answer aloud and is cancelled while the mic is open. |
| `listener.js` | Shared microphone for both pages. Uses the browser speech engine. A short pause locks the current words so the next sound is a new word. About 1.2 seconds of silence, or Done, sends the sentence. |
| `recorder.js` | Records one phrase, ends it on silence, and sends it to `/api/transcribe` (local Whisper). `AutoListener` uses it when the server reports `transcribe`, else the browser engine in `listener.js`. |
| `dashboard.css` | Layout, colors, and dialogs for the main page. |
| `styles.css` | Styles for the login page. |
| `agent.html` | The second page, at `/agent`. A circle in the center, a live caption, and the transcript. |
| `agent.css` | Layout for that page. |
| `agent.js` | Tap the circle to listen. Waves follow the microphone while you speak, then move while the reply is read aloud. The same `/api/talk` call as the development page writes both lines into the transcript. |

Voice examples the page suggests:

- “Register him as Raj”
- “Raj needs to take medicine at 8 AM and 8 PM”
- “What's due now?”
- “Switch to caregiver mode”

The script tag in `index.html` includes a `?v=` query so a refresh picks up a new `app.js` after that number changes.

Recognition accuracy depends on the browser's speech engine and microphone. The waveform meter requests echo cancellation and noise suppression; those constraints do not configure the separate browser speech-recognition engine. Permission errors and speech that never finalizes do not submit a command. Physical microphone testing is still required.

Run the listener regression tests with Node.js 18 or newer:

```bash
node --test tests/listener.test.cjs
```

The result handling follows the [Web Speech result lifecycle](https://developer.mozilla.org/en-US/docs/Web/API/SpeechRecognitionEvent/results).
