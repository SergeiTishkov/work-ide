-- Named queries over schemas/db.sql, shared by tools/selections.py,
-- tools/feedback.py and the desktop app (app/main/store.js).
-- `-- name: <name>` starts a query; parameters are named (:name).
--
-- FRESH. A vacancy is fresh when no selection before the latest real run
-- (kind = 'run') contained it. The baseline is the run, not simply the previous
-- selection: a rebuild (re-selecting after a filter fix, without fetching)
-- would otherwise make nothing fresh at all, although nothing was read yet.
-- With no run recorded yet, everything is fresh.
--
-- DECIDED EARLIER. A selection shows the feedback given during the current
-- collection only: since the latest real run (rebuilds belong to the run they
-- follow). A vacancy decided in an earlier collection — rejected a month ago,
-- or carried over from before selections existed (no feedback_selection_id) —
-- is settled and appears in none of the filters; otherwise "rejected" and
-- "all" fill up with old decisions (the owner, 2026-09-30).
--
-- LIMIT. The LIST shows vacancies without feedback up to section_limit per
-- class, ranked AFTER the filter, so "fresh without feedback" shows the top of
-- the fresh ones. :shown ('{"hot_lead": 25}') raises a class's limit: "Show
-- more" and the scroll add ten at a time (the owner, 2026-10-04). A class the
-- person expanded (:expanded, ",hot_lead,...,") shows all of them. Vacancies
-- with feedback are never capped. The COUNTS are
-- never capped either: a count is how many there are, not how many rows are
-- on screen — capped counts did not add up across markets (the owner,
-- 2026-09-30: UK 40 + ANZ 15 > "everything" 54), and the list says "N more"
-- under a capped class instead.
--
-- SOURCE. Every listing and count takes :source, the board a vacancy came
-- from ('' for all of them), and applies it together with the status filter
-- (the owner, 2026-10-04: "both work at the same time"). It is read from the
-- view, where report.vacancy_view puts it, and from the record for views
-- written before that.
--
-- FIT. The listing, the counts and the source list take :fit, one class
-- ('' for all of them): the third drop-down next to "Show" and "Source".
-- The class totals do not: they are that drop-down's own numbers.

-- name: latest_selection
SELECT MAX(id) AS id FROM selections;

-- name: selection
SELECT id, run, created_at, kind FROM selections WHERE id = :selection_id;

-- name: segments
SELECT slug, name, position, is_default
FROM selection_segments
WHERE selection_id = :selection_id
ORDER BY position;

-- name: display_name
SELECT value FROM meta WHERE key = 'display_name';

-- name: source_sites
-- {source name: website} as JSON, from config/sources.catalog.yaml, written
-- with every selection (selections.write_source_sites).
SELECT value FROM meta WHERE key = 'source_sites';

-- name: listing
WITH baseline AS (
  SELECT MAX(id) AS id FROM selections WHERE kind = 'run' AND id <= :selection_id
),
base AS (
  SELECT i.vacancy_id, i.class, i.class_position, i.section_limit, i.score,
         i.eligibility_rank, v.view, v.views, v.feedback_status, v.rejected_reason,
         v.bugged_reason, v.feedback_at, v.applied_at, v.contact_comment, v.contact_at,
         v.interview_comments, v.interview_at, v.final_comment, v.final_at,
         v.awaiting_offer_comment, v.awaiting_offer_at, v.declined_comment, v.declined_at,
         v.offered_comment, v.offered_at, v.started_comment, v.started_at,
         CASE
           WHEN (SELECT id FROM baseline) IS NULL THEN 1
           WHEN EXISTS (SELECT 1 FROM selection_items o
                        WHERE o.vacancy_id = i.vacancy_id
                          AND o.selection_id < (SELECT id FROM baseline)) THEN 0
           ELSE 1
         END AS fresh
  FROM selection_items i
  JOIN vacancies v ON v.id = i.vacancy_id
  WHERE i.selection_id = :selection_id AND i.segment = :segment
    AND (v.feedback_status = 'new'
         OR v.feedback_selection_id >= COALESCE((SELECT id FROM baseline), 0))
    AND (:source = '' OR COALESCE(json_extract(v.view, '$.source'), json_extract(v.data, '$.source')) = :source)
    AND (:fit = '' OR i.class = :fit)
),
filtered AS (
  SELECT * FROM base
  WHERE CASE :filter
          WHEN 'fresh_new' THEN fresh = 1 AND feedback_status = 'new'
          WHEN 'no_feedback' THEN feedback_status = 'new'
          WHEN 'all'       THEN 1
          WHEN 'fresh'     THEN fresh = 1
          ELSE feedback_status = :filter
        END
),
ranked AS (
  SELECT *, ROW_NUMBER() OVER (
           PARTITION BY class, feedback_status = 'new'
           ORDER BY score DESC, eligibility_rank, vacancy_id) AS rank_in_class
  FROM filtered
)
SELECT vacancy_id, class, score, eligibility_rank, fresh, view, views, feedback_status,
       rejected_reason, bugged_reason, feedback_at, applied_at, contact_comment,
       contact_at, interview_comments, interview_at, final_comment, final_at,
       awaiting_offer_comment, awaiting_offer_at, declined_comment, declined_at,
       offered_comment, offered_at, started_comment, started_at
FROM ranked
WHERE feedback_status <> 'new'
   OR rank_in_class <= COALESCE(json_extract(:shown, '$.' || class), section_limit)
   OR instr(:expanded, ',' || class || ',') > 0
ORDER BY class_position, score DESC, eligibility_rank, vacancy_id;

-- name: listing_counts
-- How many vacancies each filter holds — the whole number, not the rows shown.
WITH baseline AS (
  SELECT MAX(id) AS id FROM selections WHERE kind = 'run' AND id <= :selection_id
),
base AS (
  SELECT i.class, v.feedback_status,
         CASE
           WHEN (SELECT id FROM baseline) IS NULL THEN 1
           WHEN EXISTS (SELECT 1 FROM selection_items o
                        WHERE o.vacancy_id = i.vacancy_id
                          AND o.selection_id < (SELECT id FROM baseline)) THEN 0
           ELSE 1
         END AS fresh
  FROM selection_items i
  JOIN vacancies v ON v.id = i.vacancy_id
  WHERE i.selection_id = :selection_id AND i.segment = :segment
    AND (v.feedback_status = 'new'
         OR v.feedback_selection_id >= COALESCE((SELECT id FROM baseline), 0))
    AND (:source = '' OR COALESCE(json_extract(v.view, '$.source'), json_extract(v.data, '$.source')) = :source)
    AND (:fit = '' OR i.class = :fit)
)
SELECT COALESCE(SUM(fresh = 1 AND feedback_status = 'new'), 0) AS fresh_new,
       COALESCE(SUM(feedback_status = 'new'), 0)               AS no_feedback,
       COUNT(*)                                                AS "all",
       COALESCE(SUM(fresh = 1), 0)                             AS fresh,
       COALESCE(SUM(feedback_status = 'applied'), 0)           AS applied,
       COALESCE(SUM(feedback_status = 'rejected'), 0)          AS rejected,
       COALESCE(SUM(feedback_status = 'bugged'), 0)            AS bugged,
       COALESCE(SUM(feedback_status = 'expired'), 0)           AS expired
FROM base;

-- name: listing_class_totals
-- Per class, how many the filter holds: the list says "N more" under a
-- capped class.
WITH baseline AS (
  SELECT MAX(id) AS id FROM selections WHERE kind = 'run' AND id <= :selection_id
),
base AS (
  SELECT i.class, v.feedback_status,
         CASE
           WHEN (SELECT id FROM baseline) IS NULL THEN 1
           WHEN EXISTS (SELECT 1 FROM selection_items o
                        WHERE o.vacancy_id = i.vacancy_id
                          AND o.selection_id < (SELECT id FROM baseline)) THEN 0
           ELSE 1
         END AS fresh
  FROM selection_items i
  JOIN vacancies v ON v.id = i.vacancy_id
  WHERE i.selection_id = :selection_id AND i.segment = :segment
    AND (v.feedback_status = 'new'
         OR v.feedback_selection_id >= COALESCE((SELECT id FROM baseline), 0))
    AND (:source = '' OR COALESCE(json_extract(v.view, '$.source'), json_extract(v.data, '$.source')) = :source)
)
SELECT class, COUNT(*) AS total
FROM base
WHERE CASE :filter
        WHEN 'fresh_new' THEN fresh = 1 AND feedback_status = 'new'
        WHEN 'no_feedback' THEN feedback_status = 'new'
        WHEN 'all'       THEN 1
        WHEN 'fresh'     THEN fresh = 1
        ELSE feedback_status = :filter
      END
GROUP BY class;

-- name: listing_sources
-- The "Source" drop-down: the boards of one market under the status filter,
-- and how many each holds. The source filter itself does not apply, so the
-- list always offers every board.
WITH baseline AS (
  SELECT MAX(id) AS id FROM selections WHERE kind = 'run' AND id <= :selection_id
),
base AS (
  SELECT COALESCE(json_extract(v.view, '$.source'), json_extract(v.data, '$.source')) AS source, v.feedback_status,
         CASE
           WHEN (SELECT id FROM baseline) IS NULL THEN 1
           WHEN EXISTS (SELECT 1 FROM selection_items o
                        WHERE o.vacancy_id = i.vacancy_id
                          AND o.selection_id < (SELECT id FROM baseline)) THEN 0
           ELSE 1
         END AS fresh
  FROM selection_items i
  JOIN vacancies v ON v.id = i.vacancy_id
  WHERE i.selection_id = :selection_id AND i.segment = :segment
    AND (v.feedback_status = 'new'
         OR v.feedback_selection_id >= COALESCE((SELECT id FROM baseline), 0))
    AND (:fit = '' OR i.class = :fit)
)
SELECT source, COUNT(*) AS total
FROM base
WHERE CASE :filter
        WHEN 'fresh_new' THEN fresh = 1 AND feedback_status = 'new'
        WHEN 'no_feedback' THEN feedback_status = 'new'
        WHEN 'all'       THEN 1
        WHEN 'fresh'     THEN fresh = 1
        ELSE feedback_status = :filter
      END
GROUP BY source
ORDER BY total DESC, source;

-- name: pipeline_running
-- The latest run still marked running. Whether it is really alive is decided
-- by the reader from heartbeat_at (and the pid, on the same host).
SELECT id, started_at, heartbeat_at, stage, pid, host
FROM pipeline_runs
WHERE status = 'running'
ORDER BY id DESC
LIMIT 1;

-- name: set_feedback
-- The first answer on a vacancy. "applied" dates the start of the funnel;
-- going back to "new" forgets everything the funnel recorded.
UPDATE vacancies
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
WHERE id = :id;

-- name: funnel_listing
-- THE FUNNEL (applied, contacted, interview, awaiting_final, awaiting_offer,
-- declined, offered, started) is the person's
-- applications, which live for weeks: its filters list every vacancy in that
-- status, whatever the collection, selection or market — a later run must
-- not make an application disappear. Newest step first.
SELECT v.id AS vacancy_id,
       json_extract(v.view, '$.classification') AS class,
       COALESCE(json_extract(v.view, '$.score'), 0) AS score,
       0 AS eligibility_rank, 0 AS fresh, v.view, v.views, v.feedback_status,
       v.rejected_reason, v.bugged_reason, v.feedback_at, v.applied_at, v.contact_comment, v.contact_at, v.interview_comments, v.interview_at, v.final_comment, v.final_at,
       v.awaiting_offer_comment, v.awaiting_offer_at, v.declined_comment, v.declined_at,
       v.offered_comment, v.offered_at, v.started_comment, v.started_at
FROM vacancies v
WHERE v.feedback_status = :filter AND v.view IS NOT NULL
  AND (:source = '' OR COALESCE(json_extract(v.view, '$.source'), json_extract(v.data, '$.source')) = :source)
  AND (:fit = '' OR json_extract(v.view, '$.classification') = :fit)
ORDER BY v.feedback_at DESC, v.id;

-- name: funnel_counts
SELECT COALESCE(SUM(feedback_status = 'applied'), 0)        AS applied,
       COALESCE(SUM(feedback_status = 'contacted'), 0)      AS contacted,
       COALESCE(SUM(feedback_status = 'interview'), 0)      AS interview,
       COALESCE(SUM(feedback_status = 'awaiting_final'), 0) AS awaiting_final,
       COALESCE(SUM(feedback_status = 'awaiting_offer'), 0) AS awaiting_offer,
       COALESCE(SUM(feedback_status = 'declined'), 0)       AS declined,
       COALESCE(SUM(feedback_status = 'offered'), 0)        AS offered,
       COALESCE(SUM(feedback_status = 'started'), 0)        AS started
FROM vacancies v
WHERE v.view IS NOT NULL
  -- only the funnel's rows: the source below reads JSON, not over the whole base
  AND v.feedback_status IN ('applied', 'contacted', 'interview', 'awaiting_final',
                            'awaiting_offer', 'declined', 'offered', 'started')
  AND (:source = '' OR COALESCE(json_extract(v.view, '$.source'), json_extract(v.data, '$.source')) = :source)
  AND (:fit = '' OR json_extract(v.view, '$.classification') = :fit);

-- name: funnel_sources
-- The "Source" drop-down under a funnel filter: every application in that
-- status, by board.
SELECT COALESCE(json_extract(v.view, '$.source'), json_extract(v.data, '$.source')) AS source, COUNT(*) AS total
FROM vacancies v
WHERE v.feedback_status = :filter AND v.view IS NOT NULL
  AND (:fit = '' OR json_extract(v.view, '$.classification') = :fit)
GROUP BY source
ORDER BY total DESC, source;

-- name: vacancy_progress
SELECT id, feedback_status, feedback_at, rejected_reason, bugged_reason, applied_at, contact_comment, contact_at, interview_comments, interview_at, final_comment, final_at,
       awaiting_offer_comment, awaiting_offer_at, declined_comment, declined_at,
       offered_comment, offered_at, started_comment, started_at
FROM vacancies WHERE id = :id;

-- name: write_progress
-- Written by the app only, after renderer/funnel.js worked out the step.
UPDATE vacancies
SET feedback_status = :status, feedback_at = :at,
    rejected_reason = :rejected_reason, bugged_reason = :bugged_reason,
    applied_at = :applied_at, contact_comment = :contact_comment, contact_at = :contact_at,
    interview_comments = :interview_comments, interview_at = :interview_at,
    final_comment = :final_comment, final_at = :final_at,
    awaiting_offer_comment = :awaiting_offer_comment, awaiting_offer_at = :awaiting_offer_at,
    declined_comment = :declined_comment, declined_at = :declined_at,
    offered_comment = :offered_comment, offered_at = :offered_at,
    started_comment = :started_comment, started_at = :started_at
WHERE id = :id;

-- name: pending_feedback_counts
-- Feedback is pending review until feedback.py marks it reviewed AFTER it was
-- last changed: a person may change their mind about a vacancy already
-- reviewed, and the new verdict deserves a look of its own.
SELECT COALESCE(SUM(feedback_status = 'bugged'), 0)   AS bugged,
       COALESCE(SUM(feedback_status = 'rejected'), 0) AS rejected
FROM vacancies
WHERE feedback_status IN ('bugged', 'rejected')
  AND (feedback_reviewed_at IS NULL OR feedback_reviewed_at < feedback_at);
