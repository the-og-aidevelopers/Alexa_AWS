# `src/dose_check`

Python package for Family Dose Check. Run the app from the repository root with `PYTHONPATH=src` so this package imports as `dose_check`.

| File | What it is for |
| --- | --- |
| `__init__.py` | Package version (`0.1.0`). |
| `server.py` | Starlette app and the MCP server. Serves the web page, `/api/talk`, schedule and today routes, and Streamable HTTP at `/mcp`. The six tools are `list_due_doses`, `log_dose`, `dose_status`, `summarize_day`, `register_person`, and `add_medicine`. `/api/talk` asks `agent.decide` which tool to call, then calls that tool through an MCP client pointed at this same server. |
| `agent.py` | Turns one spoken sentence into a speaker (older adult or caregiver) and a tool call. Mode phrases such as “switch to caregiver mode” are handled here. Tool choice uses local rules unless `AGENT_WITH_BEDROCK=1`. |
| `intent.py` | Local speech rules: repair common mishearings, register a person, add a medicine time, log a dose, ask what is due, and summarize the day. |
| `service.py` | Dose rules applied to the database: who is due, logging taken or skipped, registering a person, and adding medicine times. Builds the sentences the app speaks. |
| `db.py` | SQLite `Store`. Tables are `people`, `schedules`, and `dose_logs`. Seeds Mom’s lisinopril when the database is empty. |
| `logic.py` | Clock math. A dose is due from 90 minutes before its time until 30 minutes after. After that it is overdue. Also maps “morning” and similar words onto a clock time. |
| `mcp_client.py` | MCP client used by `/api/talk` and the live server test. Connects with Streamable HTTP and reads `protocol_version`. |
| `speech.py` | Optional Bedrock rephrase of a tool’s sentence. Off unless `SPEAK_WITH_BEDROCK=1`. A failed call keeps the original sentence. |
