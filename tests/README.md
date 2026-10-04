# `tests`

```bash
PYTHONPATH=src AGENT_WITH_BEDROCK=0 pytest
```

Run that from the repository root. `AGENT_WITH_BEDROCK=0` keeps the suite on the local speech rules.

| File | What it is for |
| --- | --- |
| `test_dose_check.py` | Dose windows, logging, skip reasons, speech routing, voice registration, medicine times, and switching caregiver mode in the same sentence as a question. Uses a temporary SQLite file. |
| `test_server.py` | Starts the real app, checks that `/mcp` lists all six tools, and checks that `POST /api/talk` reaches a tool over Streamable HTTP. It stops that process when the test ends. |
