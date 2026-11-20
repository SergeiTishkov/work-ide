# 0128 Architecture review: duplicates and structure

Source: the owner, 2026-11-20
Scope: tools, app, docs

## Business
The owner, 2026-11-20, after the availability work (task 0127): an
architecture review at the end, to tidy the application up: remove
duplicates, improve the structure.

## Implementation
Two read-only reviews (Python `tools/`, Electron `app/`) list the
duplicates, dead code and lists kept in sync by hand, each with file and
line. The findings are checked against the code; the small, low-risk ones
are done here with tests, the larger ones become items or triage tasks.

## Items
- DONE - The two reviews (2026-11-20)
- DONE - App: the i18n parameter tests matched `{w}` only (a missing backslash) and checked nothing; fixed, with a check that they find parameters
- DONE - App: a class without a section label (low_priority, rejected, remote_unconfirmed rows kept by the applications view) sorted first and showed its raw key; now last, named as in the clean-up
- DONE - App: comments naming files that no longer exist (main/tasks.js, reputation.js, cv.js, batch.js, rest.js, runner.js) point at what replaced them; `QueueClient.active()`, a duplicate of `AGES` and two orphaned comments removed
- DONE - App: the Electron smoke test failed since 2026-10-23 (the filters' card starts folded in a fresh profile); it opens the card
- DONE - Tools: dead code removed (cv_docx.plain_text, fetch_jobserve._TITLE_ALT_RE, fetch_linkedin._fetch_description, fetch_wwr.FEED_URL, score._target_market_of and its cache, segments.group_name and counts_by_group, settings.DELETED; nothing referenced them)
- DONE - Tools: `reputation_lookup.refresh_company` rendered the rows with a copy of `selections.refresh_views` that skipped the company kinds; it calls refresh_views
- DONE - Tools: the clean-up filter check written twice (taskd, schedules) is `taskq.clean_filters`; `enrich_descriptions.HEAD_CLASSES` is `report.LISTED_CLASSES`, its LinkedIn pause `fetch_linkedin.PAUSE_SECONDS`
- DONE - Tools: a clean-up counted ages from the local date, the app's AGE from SQLite's UTC date('now'); for the hours around midnight a band chosen in the app deleted by another day. `cleanup.utc_today`, with a test against SQLite
- DONE - `tests/test_vocabulary_sync.py`: statuses (db.sql CHECK, db, selections, funnel.js, store.js, cleanup.js, app.js), filter bands, classes (report, cleanup, cleanup.js, app.js sections), task kinds and schedules (taskq, schedules, queue.js), identity and vacancy patterns (identity, taskq, taskd, documents, four JS files) must agree
- TO DO - App: one helper for the four comment forms (reason, funnel step, instructions, timeline edit) and one for the six dialogs, all drawn into modal-host with one Escape path (clean-up, identities and sources do not close on Escape)
- TO DO - App: UTC times shown as local (`run.collecting_since`, the selection caption); one date/time formatter
- TO DO - App: one runner for Python from main (taskq, cleanup, documents, identities each wrap execFile; identities.js sets no PYTHONIOENCODING; clean-up runs the root's tools, taskq the app's own)
- TO DO - Tools: one `claude -p` wrapper (cv_tailor, ai_brief, ai_screen, reputation_lookup, taskd probes); one schema.org JobPosting reader (enrich_descriptions, fetch_linkedin, fetch_djinni); the ATS endpoint table once (fetch_ats, apply_channels); public names for the private functions used across modules (cover_letter on cv_tailor, availability on link_check and fetch_linkedin, selections on report)
- TO DO - Tools: `score._AVOIDED_MARKETS_CACHE` is keyed by `id(profile)`, which Python may reuse for another profile after the first is freed; key it by content
- TO DO - Tools: fetcher scaffolding (an HTTP GET helper, an HTML fragment cleaner, `_configured_params` in five fetchers, 18 `main()`s without `skip_if_inactive`, salary formatters, the "country of Georgia" rewrite in three fetchers)
- TO DO - Split renderer/app.js (3,500 lines) along its sections into classic scripts sharing one namespace, after the helpers above; split score.py's location and compensation parts out
