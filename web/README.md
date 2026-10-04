# `web`

Browser simulator. `server.py` serves `index.html` at `/` and these files under `/static`.

| File | What it is for |
| --- | --- |
| `index.html` | Page layout: schedule rail, talk panel, and today’s board. The schedule form adds a dose with the mouse. The talk box is the voice path. |
| `app.js` | Page behavior. Sends each utterance to `POST /api/talk`, refreshes the board from `GET /api/today`, and adds or removes doses through `/api/schedules`. Suggested phrases are the chips above the transcript. “Speak replies” reads the answer aloud and is cancelled while the mic is open. |
| `listener.js` | Shared browser speech lifecycle for both pages. Combines the preferred result from each sentence segment, replaces interim guesses, and sends only finalized speech. A 1.2-second pause or Done requests a stop; final results can arrive before recognition ends. Sessions stop after 20 seconds and clear timers on cancellation or errors. |
| `styles.css` | Layout and colors for the three panels. |
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
