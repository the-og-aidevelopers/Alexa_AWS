# `tests`

`test_agent.py` covers all six model-selected tools with a mocked Bedrock response, rejecting malformed arguments and checking local fallback. `test_talk_concurrency.py` checks that a blocked provider call does not block a health request. These do not establish live AWS model access or speech accuracy.

`listener.test.cjs` exercises interim corrections, multi-segment speech, final-result draining, duplicate callbacks, retries, and cancellation using Node's built-in test runner. Run `node --test tests/listener.test.cjs` from the repository root.

```bash
PYTHONPATH=src AGENT_WITH_BEDROCK=0 pytest
```

Run that from the repository root. `AGENT_WITH_BEDROCK=0` keeps the suite on the local speech rules.

| File | What it is for |
| --- | --- |
| `test_dose_check.py` | Dose windows, logging, skip reasons, speech routing, voice registration, medicine times, and switching caregiver mode in the same sentence as a question. Uses a temporary SQLite file. |
| `test_server.py` | Starts the real app, checks that `/mcp` lists all six tools, and checks that `POST /api/talk` reaches a tool over Streamable HTTP. It stops that process when the test ends. |
