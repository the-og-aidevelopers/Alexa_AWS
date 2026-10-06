# Family Dose Check

Spoken household medicine log for the [Amazon Developer Hackathon](https://amazonappdev2026.devpost.com/) Alexa+ track. No Echo, no phone camera, and no model training. A caregiver writes the schedule. An older adult, or the caregiver, asks about it in a web simulator that calls a self-hosted MCP server over Streamable HTTP.

About half of filled U.S. prescriptions are taken incorrectly, and that gap is tied to roughly $100–$300 billion a year in health spending ([CDC MMWR, 2017](https://www.cdc.gov/mmwr/volumes/66/wr/mm6645a2.htm)). This project is the reminder-and-family-check pattern from that brief: a log the household can hear.

## Run

From the repository root:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
PYTHONPATH=src uvicorn dose_check.server:app --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000 and create a local caregiver account at `/login` for the dashboard. Open http://127.0.0.1:8000/agent for the circle you tap to talk.

If port 8000 is already in use, start on another port and open that URL instead:

```bash
PYTHONPATH=src uvicorn dose_check.server:app --host 127.0.0.1 --port 8010
```

If this machine already has `mcp`, `uvicorn`, `starlette`, `httpx`, `boto3`, and `pytest` installed, skip the virtualenv and run the `uvicorn` line directly.

The first launch creates `data/dose_check.sqlite`. Each caregiver account gets a private, empty household. Add a person and their schedule to try the demo lines below. For the old seeded Mom/lisinopril demo only, explicitly set `DOSE_AUTH_PROVIDER=demo` on localhost.

Set `DOSE_DB` to use a different SQLite file. Set `AGENT_WITH_BEDROCK=0` to keep tool choice on the local rules.

## Demo lines

Type them, or use Mic. The browser listens until you pause, then sends the phrase. Hard-refresh the page after a code update so the latest `app.js` loads.

Older adult:

- What's due now?
- I took the morning one
- I skipped the evening one, I feel dizzy
- Register him as Raj
- Raj needs to take medicine at 8 AM and 8 PM
- Switch to caregiver mode

Caregiver:

- Did Mom take her evening medicine?
- Did Mom take her morning medicine?
- How did today go?
- Add this person, register her as Priya
- Priya needs to take lisinopril in the morning and the evening
- Switch to older adult mode

Clock times are stored as said. Morning, afternoon, evening, and night become 8:00 AM, 2:00 PM, 8:00 PM, and 9:00 PM. A person with no medicine yet still appears on the schedule.

## Layout

Each directory has a short note on the files in it:

- [src/dose_check/README.md](src/dose_check/README.md) — server, tools, speech routing, and storage
- [web/README.md](web/README.md) — the browser simulator
- [tests/README.md](tests/README.md) — what the tests cover
- [data/README.md](data/README.md) — the SQLite file created at runtime

## MCP

The server is the official Python MCP SDK (`MCPServer`) on Streamable HTTP, stateless JSON responses, at `http://127.0.0.1:8000/mcp`. The handshake version is 2025-11-25 or later. Local MCP callers must forward the authenticated session cookie; Cognito clients must provide a verified access token. The simulator does not call the dose functions directly: `/api/talk` opens an MCP client to that endpoint.

Tools:

- `list_due_doses`
- `log_dose`
- `dose_status`
- `summarize_day`
- `register_person`
- `add_medicine`

Answers come from SQLite. A dose is due from 90 minutes before the scheduled time until 30 minutes after. Past that grace window it is overdue, and the Today panel shows a family alert.

## AWS, optional

AWS stays disconnected by default, even when credentials exist. See [AWS readiness](docs/aws-readiness.md) and [.env.example](.env.example) for the local account flow, Cognito adapter, connection steps, and remaining deployment work.

Only when you deliberately connect AWS later:

```bash
export AWS_ENABLED=1
export AGENT_WITH_BEDROCK=1
export SPEAK_WITH_BEDROCK=0
export AWS_REGION=us-east-1
export BEDROCK_MODEL_ID=amazon.nova-micro-v1:0
```

Bedrock routing requires both `AWS_ENABLED=1` and `AGENT_WITH_BEDROCK=1`. Optional `SPEAK_WITH_BEDROCK=1` adds a response rephrasing call. The old automatic credential detection is removed. This repository does not provision or deploy AWS resources at startup.

Model-selected tools must match the six known tools and their argument schemas. Invalid statuses, missing required arguments, unexpected fields, and multiple tool requests fall back to the local sentence router. Model calls run outside the web event loop, with a 3-second connection timeout, a 10-second response timeout, and no retries. Failed rephrasing keeps the template. There is no SageMaker job and no always-on model.

## Tests

```bash
PYTHONPATH=src pytest
node --test tests/listener.test.cjs
```

## What this is not

It does not diagnose, change a prescription, or talk to a pharmacy. It is a household log.
