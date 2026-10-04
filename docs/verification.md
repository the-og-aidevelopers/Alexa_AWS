# ayushm verification

## Scope

Related to #1: both browser pages now use one listener that rebuilds the current transcript from preferred recognition results, joins segments, replaces interim guesses, and sends finalized speech once. Stop waits for the final-result/end events. Errors, cancellation, stale callbacks, and timers cannot submit an old session. The waveform microphone starts independently so permission setup does not delay recognition; late streams are released.

Related to #3: the existing Bedrock agent already selected the six MCP tools. Its output now passes schema validation before routing. Invalid statuses no longer become `taken`; unknown tools, unexpected fields, and multiple requests fall back to local routing. Synchronous model calls run outside the server event loop with connection/read timeouts and no retries. Mode parsing preserves the user's original case and apostrophes in skip reasons.

No changes to `test.txt`.

## Validation

- `PYTHONPATH=src AGENT_WITH_BEDROCK=0 python -m pytest -q`: **35 passed**, including a real server and Streamable HTTP MCP handshake/tool calls, mocked Bedrock outputs, and concurrent health requests during blocked model calls.
- `node --test tests/listener.test.cjs`: **14 passed**.
- `node --check` passed for all three browser scripts; `git diff --check` passed.
- Chromium/Playwright acceptance against a temporary SQLite database: both pages loaded without page errors; typed status query and simulated speech reached the real local MCP server; multi-segment skipped-dose command preserved `I feel dizzy`; the development mic recovered from `no-speech`; the agent page returned a day summary and reset to idle.

The browser test injected SpeechRecognition events. It did not establish physical microphone accuracy or noise performance. The agent-browser daemon could not start in this execution environment, so acceptance used Playwright with an npm-provided Chromium binary. Proxy variables were removed for local Python integration tests because this environment's SOCKS proxy dependencies were unavailable.

## Remaining decisions and acceptance

- **#1:** physical microphone testing in the target browser, including short pauses, a noisy room, and medicine/person names. Browser recognition accuracy depends on the engine; waveform noise-suppression constraints do not configure that engine.
- **#2:** choose the login provider and define household access/roles. Merely selecting caregiver mode is not authentication.
- **#3:** test valid routing and fallback with actual AWS credentials/model access. Unit tests mock Bedrock and do not prove deployment credentials or model availability.
- **#4:** UI issue explicitly says to do it last; visual requirements are unspecified.
- **#5:** AWS hosting/storage/identity choices require an architecture decision. No AWS resources were created.
- **#6:** speaker identification requires an enrollment/data/provider design and validation; recognition of spoken words does not identify a person.

Issues remain open pending those decisions or live acceptance checks.
