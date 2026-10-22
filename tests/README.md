# `tests`

`test_agent.py` covers all six model-selected tools with a mocked Bedrock response, rejecting malformed arguments and checking local fallback. `test_talk_concurrency.py` checks that a blocked provider call does not block a health request. These do not establish live AWS model access or speech accuracy.

`listener.test.cjs` checks the browser speech listener: alternatives, a short pause starting a new word, and cancellation. Run `node --test tests/listener.test.cjs` from the repository root.

```bash
PYTHONPATH=src AGENT_WITH_BEDROCK=0 pytest
```

Run that from the repository root. Provider tests use mocks or locally signed tokens, and integration servers explicitly disable AWS.

| File | What it is for |
| --- | --- |
| `test_dose_check.py` | Dose windows, logging, skip reasons, speech routing, voice registration, medicine times, and switching caregiver mode in the same sentence as a question. Uses a temporary SQLite file. |
| `test_auth.py` | Local account/session lifecycle and cross-household REST/MCP isolation, scoped storage, offline RSA-signed Cognito token acceptance/rejection. |
| `test_aws_offline.py` | Ensures the global opt-in blocks AWS client creation and credential discovery, including when feature flags are enabled. |
| `test_server.py` | Starts the real app, checks that `/mcp` lists all six tools, and checks that `POST /api/talk` reaches a tool over Streamable HTTP. It stops that process when the test ends. |

- `frontend/src/__tests__` covers the React screens with Vitest.
- `test_transcribe.py` and `recorder.test.cjs` cover the local transcription endpoint, the prompt, and the recording listener with mocked audio.
