# Self-Healing Docs (parked)

Parked on purpose: the team decided to build the Impact Analyzer and Dependency Map first.

`docdrift.py` is the v1 engine. It compares code before and after a finished Jira story and looks for:
- renamed or removed functions,
- removed API response fields,
- new config keys that no document mentions.

For each finding it drafts a minimal fix for the affected doc section, and a human approves it.

It is **not imported** by the app. To revive it, adapt it to the new `mapbuild` model (`backend/app/mapbuild/model.py`): docs become nodes that "mention" endpoints, tables and config keys.
