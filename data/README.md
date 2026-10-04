# `data`

Runtime storage only. Nothing in here is source code.

| File | What it is for |
| --- | --- |
| `.gitkeep` | Keeps this directory in git while the database file stays out of it. |
| `dose_check.sqlite` | Created on first launch. Holds people, medicine times, and today’s taken or skipped log. It is listed in `.gitignore`. Delete it to seed Mom’s lisinopril again. Point `DOSE_DB` at another path to use a different file. |
