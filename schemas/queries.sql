-- Named queries over schemas/db.sql, shared by tools/selections.py,
-- tools/feedback.py and the desktop app (app/main/store.js).
-- `-- name: <name>` starts a query; parameters are named (:name).
--
-- IDENTITY. The base holds every identity; every query takes :identity, the
-- prefix, and reads that identity's selections and its rows of
-- vacancy_identity only. Selection ids are shared by all identities, so
-- "earlier selections" always means the identity's own.
--
-- FRESH. A vacancy is fresh when no selection of the identity before its
-- latest real run (kind = 'run') contained it. The baseline is the run, not
-- simply the previous selection: a rebuild (re-selecting after a filter fix,
-- without fetching) would otherwise make nothing fresh at all, although
-- nothing was read yet. With no run recorded yet, everything is fresh.
--
-- DECIDED EARLIER. A selection shows the feedback given during the current
-- collection only: since the latest real run (rebuilds belong to the run they
-- follow). A vacancy decided in an earlier collection — rejected a month ago,
-- or carried over from before selections existed (no feedback_selection_id) —
-- is settled and appears in none of the filters; otherwise "rejected" and
-- "all" fill up with old decisions (the owner, 2026-09-30).
--
-- THE VIEW. The app's four drop-downs (the owner, 2026-10-07) each choose
-- several rows, so a query takes lists, as JSON arrays:
--   :segments  the markets (selection_segments.slug); the app sends the
--              market with everything = 1 for "all markets";
--   :statuses  feedback statuses: 'new' ("not applied or denied"), the
--              funnel's (applications) and 'rejected'/'bugged'/'expired'
--              (denied);
--   :fresh     1 (fresh), 0 (seen in an earlier run), or both;
--   :sources   boards, NULL for every board (new boards included);
--   :fits      classes, NULL for every class;
--   :companies NULL for every company, or {"kinds": [...], "hidden": [...]}:
--              the kinds shown ('marketplace', 'agency', 'reposter',
--              'other') and the intermediaries hidden among them, by name.
--              Hidden names, not shown ones, so an intermediary a later run
--              brings is listed (the owner, 2026-10-14);
--   :ages      NULL for any age, or the ages chosen (see AGE).
-- A row is shown when its status is one of :statuses AND its freshness one
-- of :fresh, and the board, class, company and age match. view_pool is what all
-- five queries read; `-- include: view_pool` stands for its text (the
-- loaders in tools/selections.py and app/main/queries.js put it in).
--
-- COMPANY KINDS. Which company is an intermediary is Python's call
-- (tools/company_kinds.py, config/company_kinds.yaml); the pipeline stores
-- the outcome in meta 'company_kinds' as {company: {kind, name}}, and a
-- company missing from it is 'other'. A base written before 2026-10-14 has
-- no such key: every company is 'other' until the next run or rebuild.
--
-- WHERE THE ROWS COME FROM. Vacancies without an answer, and the ones turned
-- down in this collection (see DECIDED EARLIER), come from the latest
-- selection, in the chosen markets. Applications live for weeks: they come
-- from every collection and every market, whatever :segments says; a later
-- run must not make an application disappear. Their freshness is counted the
-- same way as everyone's.
--
-- LIMIT. The LIST shows vacancies without feedback up to section_limit per
-- class, ranked AFTER the filter, so "fresh" shows the top of the fresh ones.
-- :shown ('{"hot_lead": 25}') raises a class's limit: "Show more" and the
-- scroll add ten at a time (the owner, 2026-10-04). A class the person
-- expanded (:expanded, ",hot_lead,...,") shows all of them. Vacancies with
-- feedback are never capped. The COUNTS are never capped either: a count is
-- how many there are, not how many rows are on screen; capped counts did not
-- add up across markets (the owner, 2026-09-30: UK 40 + ANZ 15 > "everything"
-- 54), and the list says "N more" under a capped class instead.
--
-- AGE (the owner, 2026-10-17): how long ago the employer posted it, by the
-- date the source gave (view.posted_on), else the day it reached the base
-- (view.first_seen_on). 'today' under one day, 'week' up to 7 days, 'month'
-- up to 30, 'older' beyond. Each is a band of its own: "up to a week" is
-- 'today' and 'week' checked together.
--
-- EACH DROP-DOWN'S OWN NUMBERS. A drop-down counts its rows under the other
-- drop-downs, not under itself: view_sources ignores :sources,
-- view_class_totals ignores :fits, view_companies ignores :companies,
-- view_ages ignores :ages, and view_counts counts the statuses under :fresh and the freshness under
-- :statuses.

-- name: latest_selection
SELECT MAX(id) AS id FROM selections WHERE identity_id = :identity;

-- name: selection
SELECT id, run, created_at, kind FROM selections
WHERE id = :selection_id AND identity_id = :identity;

-- name: segments
SELECT slug, name, names, position, is_default, everything
FROM selection_segments
WHERE selection_id = :selection_id
ORDER BY position;

-- name: display_name
SELECT display_name AS value FROM identities WHERE id = :identity;

-- name: source_sites
-- {source name: website} as JSON, from config/sources.catalog.yaml, written
-- with every selection (selections.write_source_sites).
SELECT value FROM meta WHERE key = 'source_sites';

-- name: view_pool
-- Not a query of its own: the common start of the five below.
runs AS (
  SELECT id, kind FROM selections WHERE identity_id = :identity
),
baseline AS (
  SELECT MAX(id) AS id FROM runs WHERE kind = 'run' AND id <= :selection_id
),
-- the intermediaries (COMPANY KINDS above). GROUP BY keeps it a table built
-- once: without it SQLite folds it into the join below and parses the meta
-- value (148 companies, 11 KB) again for every row of the pool — measured
-- 2026-10-18 on 103 000 rows: 250-560 ms a query, 1.9 s for the list's six,
-- every click; with it 30-75 ms. (MATERIALIZED would say the same, but the
-- Python side runs SQLite 3.34, older than the keyword.)
company_kinds AS (
  SELECT key AS company, json_extract(value, '$.kind') AS kind, json_extract(value, '$.name') AS name
  FROM json_each(COALESCE((SELECT value FROM meta WHERE key = 'company_kinds'), '{}'))
  GROUP BY key
),
-- a vacancy in two chosen markets is one row
in_markets AS (
  SELECT i.vacancy_id, MIN(i.class) AS class, MIN(i.class_position) AS class_position,
         MIN(i.section_limit) AS section_limit, MAX(i.score) AS score,
         MIN(i.eligibility_rank) AS eligibility_rank
  FROM selection_items i
  WHERE i.selection_id = :selection_id AND i.selection_id IN (SELECT id FROM runs)
    AND i.segment IN (SELECT value FROM json_each(:segments))
  GROUP BY i.vacancy_id
),
candidates AS (
  SELECT m.vacancy_id, m.class, m.class_position, m.section_limit, m.score,
         m.eligibility_rank, 0 AS application
  -- CROSS JOIN keeps this order: the market's rows looked up by key, not every
  -- verdict of the identity scanned (seconds on 46k rows, 2026-10-12)
  FROM in_markets m
  CROSS JOIN vacancy_identity v ON v.vacancy_id = m.vacancy_id AND v.identity_id = :identity
  WHERE v.feedback_status = 'new'
     OR (v.feedback_status IN ('rejected', 'bugged', 'expired')
         AND v.feedback_selection_id >= COALESCE((SELECT id FROM baseline), 0))
  UNION ALL
  SELECT v.vacancy_id, json_extract(v.view, '$.classification'), NULL, NULL,
         COALESCE(json_extract(v.view, '$.score'), 0), 0, 1
  FROM vacancy_identity v
  WHERE v.identity_id = :identity AND v.view IS NOT NULL
    AND v.feedback_status IN ('applied', 'contacted', 'interview', 'awaiting_final',
                              'awaiting_offer', 'declined', 'offered', 'started')
),
joined AS (
  SELECT c.*, v.view, v.views, v.feedback_status, v.rejected_reason, v.bugged_reason,
         v.feedback_at, v.applied_at, v.contact_comment, v.contact_at,
         v.interview_comments, v.interview_at, v.final_comment, v.final_at,
         v.awaiting_offer_comment, v.awaiting_offer_at, v.declined_comment, v.declined_at,
         v.offered_comment, v.offered_at, v.started_comment, v.started_at,
         COALESCE(json_extract(v.view, '$.source'), json_extract(d.data, '$.source')) AS source,
         CASE
           WHEN (SELECT id FROM baseline) IS NULL THEN 1
           WHEN EXISTS (SELECT 1 FROM selection_items o JOIN runs r ON r.id = o.selection_id
                        WHERE o.vacancy_id = c.vacancy_id
                          AND o.selection_id < (SELECT id FROM baseline)) THEN 0
           ELSE 1
         END AS fresh,
         COALESCE(k.kind, 'other') AS company_kind, k.name AS company_name,
         -- days since it was posted (AGE); no date at all reads as today
         COALESCE(julianday(date('now')) - julianday(COALESCE(
           json_extract(v.view, '$.posted_on'), json_extract(v.view, '$.first_seen_on'))), 0) AS age_days
  FROM candidates c
  CROSS JOIN vacancy_identity v ON v.vacancy_id = c.vacancy_id AND v.identity_id = :identity
  CROSS JOIN vacancies d ON d.id = c.vacancy_id
  LEFT JOIN company_kinds k ON k.company = json_extract(v.view, '$.company')
),
pool AS (
  SELECT *,
         CASE
           WHEN age_days < 1 THEN 'today'
           WHEN age_days <= 7 THEN 'week'
           WHEN age_days <= 30 THEN 'month'
           ELSE 'older'
         END AS age
  FROM joined
)

-- name: view_listing
-- Ordered by class, then: the selection's rows by score, the applications
-- after them, newest step first.
WITH
-- include: view_pool
,
matched AS (
  SELECT * FROM pool
  WHERE feedback_status IN (SELECT value FROM json_each(:statuses))
    AND fresh IN (SELECT value FROM json_each(:fresh))
    AND (:sources IS NULL OR source IN (SELECT value FROM json_each(:sources)))
    AND (:fits IS NULL OR class IN (SELECT value FROM json_each(:fits)))
    AND (:companies IS NULL
           OR (company_kind IN (SELECT value FROM json_each(:companies, '$.kinds'))
               AND COALESCE(company_name, '') NOT IN (SELECT value FROM json_each(:companies, '$.hidden'))))
    AND (:ages IS NULL OR age IN (SELECT value FROM json_each(:ages)))
),
ranked AS (
  SELECT *, ROW_NUMBER() OVER (
           PARTITION BY class, feedback_status = 'new'
           ORDER BY score DESC, eligibility_rank, vacancy_id) AS rank_in_class
  FROM matched
)
SELECT vacancy_id, class, score, eligibility_rank, fresh, view, views, feedback_status,
       rejected_reason, bugged_reason, feedback_at, applied_at, contact_comment,
       contact_at, interview_comments, interview_at, final_comment, final_at,
       awaiting_offer_comment, awaiting_offer_at, declined_comment, declined_at,
       offered_comment, offered_at, started_comment, started_at
FROM ranked r
WHERE feedback_status <> 'new'
   OR rank_in_class <= COALESCE(json_extract(:shown, '$.' || class), section_limit)
   OR instr(:expanded, ',' || class || ',') > 0
ORDER BY COALESCE(class_position,
                  (SELECT MIN(i.class_position) FROM selection_items i
                   WHERE i.selection_id = :selection_id AND i.class = r.class), 99),
         class, application,
         CASE WHEN application = 1 THEN feedback_at END DESC,
         score DESC, eligibility_rank, vacancy_id;

-- name: view_counts
-- The "Show" drop-down's numbers: (axis 'status', a status, how many) under
-- :fresh, and (axis 'fresh', '1' or '0', how many) under :statuses.
WITH
-- include: view_pool
,
base AS (
  SELECT feedback_status, fresh FROM pool
  WHERE (:sources IS NULL OR source IN (SELECT value FROM json_each(:sources)))
    AND (:fits IS NULL OR class IN (SELECT value FROM json_each(:fits)))
    AND (:companies IS NULL
           OR (company_kind IN (SELECT value FROM json_each(:companies, '$.kinds'))
               AND COALESCE(company_name, '') NOT IN (SELECT value FROM json_each(:companies, '$.hidden'))))
    AND (:ages IS NULL OR age IN (SELECT value FROM json_each(:ages)))
)
SELECT 'status' AS axis, feedback_status AS key, COUNT(*) AS total
FROM base
WHERE fresh IN (SELECT value FROM json_each(:fresh))
GROUP BY feedback_status
UNION ALL
SELECT 'fresh', CAST(fresh AS TEXT), COUNT(*)
FROM base
WHERE feedback_status IN (SELECT value FROM json_each(:statuses))
GROUP BY fresh;

-- name: view_class_totals
-- Per class, how many the view holds: the "Fit" drop-down, and "N more"
-- under a capped class.
WITH
-- include: view_pool
SELECT class, COUNT(*) AS total
FROM pool
WHERE feedback_status IN (SELECT value FROM json_each(:statuses))
  AND fresh IN (SELECT value FROM json_each(:fresh))
  AND (:sources IS NULL OR source IN (SELECT value FROM json_each(:sources)))
  AND (:companies IS NULL
         OR (company_kind IN (SELECT value FROM json_each(:companies, '$.kinds'))
             AND COALESCE(company_name, '') NOT IN (SELECT value FROM json_each(:companies, '$.hidden'))))
  AND (:ages IS NULL OR age IN (SELECT value FROM json_each(:ages)))
GROUP BY class;

-- name: view_sources
-- The "Source" drop-down: the boards the view holds, and how many each.
WITH
-- include: view_pool
SELECT source, COUNT(*) AS total
FROM pool
WHERE feedback_status IN (SELECT value FROM json_each(:statuses))
  AND fresh IN (SELECT value FROM json_each(:fresh))
  AND (:fits IS NULL OR class IN (SELECT value FROM json_each(:fits)))
  AND (:companies IS NULL
         OR (company_kind IN (SELECT value FROM json_each(:companies, '$.kinds'))
             AND COALESCE(company_name, '') NOT IN (SELECT value FROM json_each(:companies, '$.hidden'))))
  AND (:ages IS NULL OR age IN (SELECT value FROM json_each(:ages)))
GROUP BY source
ORDER BY total DESC, source;

-- name: view_companies
-- The "Company" drop-down: (kind, name, how many) for each intermediary the
-- view holds, and (kind 'other', NULL, how many) for every other company.
WITH
-- include: view_pool
SELECT company_kind AS kind, company_name AS name, COUNT(*) AS total
FROM pool
WHERE feedback_status IN (SELECT value FROM json_each(:statuses))
  AND fresh IN (SELECT value FROM json_each(:fresh))
  AND (:sources IS NULL OR source IN (SELECT value FROM json_each(:sources)))
  AND (:fits IS NULL OR class IN (SELECT value FROM json_each(:fits)))
  AND (:ages IS NULL OR age IN (SELECT value FROM json_each(:ages)))
GROUP BY company_kind, company_name
ORDER BY total DESC, kind, name;

-- name: view_ages
-- The "Age" drop-down: (age, how many) under every other drop-down.
WITH
-- include: view_pool
SELECT age, COUNT(*) AS total
FROM pool
WHERE feedback_status IN (SELECT value FROM json_each(:statuses))
  AND fresh IN (SELECT value FROM json_each(:fresh))
  AND (:sources IS NULL OR source IN (SELECT value FROM json_each(:sources)))
  AND (:fits IS NULL OR class IN (SELECT value FROM json_each(:fits)))
  AND (:companies IS NULL
         OR (company_kind IN (SELECT value FROM json_each(:companies, '$.kinds'))
             AND COALESCE(company_name, '') NOT IN (SELECT value FROM json_each(:companies, '$.hidden'))))
GROUP BY age;

-- name: pipeline_running
-- The latest run still marked running, of any identity: the base is shared,
-- so one run at a time (tools/runstate.py). Whether it is really alive is
-- decided by the reader from heartbeat_at (and the pid, on the same host).
SELECT id, identity_id, started_at, heartbeat_at, stage, pid, host
FROM pipeline_runs
WHERE status = 'running'
ORDER BY id DESC
LIMIT 1;

-- name: set_feedback
-- The first answer on a vacancy. "applied" dates the start of the funnel;
-- going back to "new" forgets everything the funnel recorded.
UPDATE vacancy_identity
SET feedback_status = :status,
    rejected_reason = :rejected_reason,
    bugged_reason = :bugged_reason,
    feedback_at = :at,
    feedback_selection_id = :selection_id,
    applied_at = CASE WHEN :status = 'applied' THEN :at
                      WHEN :status = 'new' THEN NULL ELSE applied_at END,
    contact_comment    = CASE WHEN :status = 'new' THEN NULL ELSE contact_comment END,
    contact_at         = CASE WHEN :status = 'new' THEN NULL ELSE contact_at END,
    interview_comments = CASE WHEN :status = 'new' THEN NULL ELSE interview_comments END,
    interview_at       = CASE WHEN :status = 'new' THEN NULL ELSE interview_at END,
    final_comment      = CASE WHEN :status = 'new' THEN NULL ELSE final_comment END,
    final_at           = CASE WHEN :status = 'new' THEN NULL ELSE final_at END,
    awaiting_offer_comment = CASE WHEN :status = 'new' THEN NULL ELSE awaiting_offer_comment END,
    awaiting_offer_at  = CASE WHEN :status = 'new' THEN NULL ELSE awaiting_offer_at END,
    declined_comment   = CASE WHEN :status = 'new' THEN NULL ELSE declined_comment END,
    declined_at        = CASE WHEN :status = 'new' THEN NULL ELSE declined_at END,
    offered_comment    = CASE WHEN :status = 'new' THEN NULL ELSE offered_comment END,
    offered_at         = CASE WHEN :status = 'new' THEN NULL ELSE offered_at END,
    started_comment    = CASE WHEN :status = 'new' THEN NULL ELSE started_comment END,
    started_at         = CASE WHEN :status = 'new' THEN NULL ELSE started_at END
WHERE identity_id = :identity AND vacancy_id = :id;

-- name: vacancy_progress
SELECT vacancy_id AS id, feedback_status, feedback_at, rejected_reason, bugged_reason, applied_at, contact_comment, contact_at, interview_comments, interview_at, final_comment, final_at,
       awaiting_offer_comment, awaiting_offer_at, declined_comment, declined_at,
       offered_comment, offered_at, started_comment, started_at
FROM vacancy_identity WHERE identity_id = :identity AND vacancy_id = :id;

-- name: write_progress
-- Written by the app only, after renderer/funnel.js worked out the step.
UPDATE vacancy_identity
SET feedback_status = :status, feedback_at = :at,
    rejected_reason = :rejected_reason, bugged_reason = :bugged_reason,
    applied_at = :applied_at, contact_comment = :contact_comment, contact_at = :contact_at,
    interview_comments = :interview_comments, interview_at = :interview_at,
    final_comment = :final_comment, final_at = :final_at,
    awaiting_offer_comment = :awaiting_offer_comment, awaiting_offer_at = :awaiting_offer_at,
    declined_comment = :declined_comment, declined_at = :declined_at,
    offered_comment = :offered_comment, offered_at = :offered_at,
    started_comment = :started_comment, started_at = :started_at
WHERE identity_id = :identity AND vacancy_id = :id;

-- name: pending_feedback_counts
-- Feedback is pending review until feedback.py marks it reviewed AFTER it was
-- last changed: a person may change their mind about a vacancy already
-- reviewed, and the new verdict deserves a look of its own.
SELECT COALESCE(SUM(feedback_status = 'bugged'), 0)   AS bugged,
       COALESCE(SUM(feedback_status = 'rejected'), 0) AS rejected
FROM vacancy_identity
WHERE identity_id = :identity
  AND feedback_status IN ('bugged', 'rejected')
  AND (feedback_reviewed_at IS NULL OR feedback_reviewed_at < feedback_at);
