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

## Local-first follow-up

Approved direction: prepare AWS capabilities now and connect later. Default accounts/routing/storage are local. The hard `AWS_ENABLED` gate prevents both model calls and credential discovery even when AWS credentials or individual Bedrock flags are configured. A Cognito access-token verifier and undeployed identity template provide the later connection boundary.

- `PYTHONPATH=src python -m pytest -q`: **52 passed**, including two real servers for authenticated and explicit demo Streamable HTTP flows; cross-household REST/MCP isolation; foreign schedule/log read/write/delete/reset attempts; local password/session/logout/expiry; RSA-signed Cognito tokens (invalid signatures, expired tokens, wrong issuer/client/token type, missing/unmapped subjects); AWS opt-in gate; ambiguous person attribution; original routing/concurrency tests.
- `node --test tests/listener.test.cjs`: **14 passed**.
- JavaScript syntax, JSON parsing of the undeployed Cognito template, and `git diff --check` passed.
- Chromium/Playwright acceptance: local registration, schedule creation, authenticated MCP dose logging, simulated agent-page speech summary, sign out, unauthorized-page redirect, sign in with persisted schedules, and mobile login without horizontal overflow. No page errors. Repeated after the final form/header styling changes.
- Browser acceptance deliberately set both Bedrock feature flags to 1 while `AWS_ENABLED=0`; model access remained disabled. SpeechRecognition events were injected, not recorded from a physical microphone.

No AWS resources were created, no AWS model calls were made, and `test.txt` was preserved.

## Remaining acceptance

- **#1:** physical microphone testing in the target browser, including short pauses, a noisy room, and medicine/person names. Browser recognition accuracy depends on its engine.
- **#2:** local caregiver registration/login and private households are implemented. Cognito browser hosted login, trusted membership provisioning, account migration, and live AWS acceptance remain connection work. Switching conversational mode grants no permissions.
- **#3:** test real Bedrock credentials/model access when AWS is explicitly enabled later. Mocks do not establish live model availability.
- **#4:** the caregiver/older-adult split is retained, with login/account controls added. A broader final UI redesign is deferred until feature acceptance.
- **#5:** local-first settings, Bedrock opt-in, Cognito verifier, starter template, and connection notes are implemented. Hosting/shared-storage deployment and live acceptance are deferred. The template has been parsed locally, not AWS-validated or deployed.
- **#6:** multiple-member unnamed dose logs now ask for a name. Voice biometric enrollment/matching is disabled pending provider selection, data handling, calibrated thresholds, and validation. No voiceprints or enrollment recordings are collected.

Issues remain open for the above live/deferred work; this PR does not claim complete AWS deployment or biometric recognition.
