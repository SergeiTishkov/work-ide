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
-- the fresh ones; a class the person expanded (:expanded, ",hot_lead,...,")
-- shows all of them. Vacancies with feedback are never capped. The COUNTS are
-- never capped either: a count is how many there are, not how many rows are
-- on screen — capped counts did not add up across markets (the owner,
-- 2026-09-30: UK 40 + ANZ 15 > "everything" 54), and the list says "N more"
-- under a capped class instead.

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

-- name: listing
WITH baseline AS (
  SELECT MAX(id) AS id FROM selections WHERE kind = 'run' AND id <= :selection_id
),
base AS (
  SELECT i.vacancy_id, i.class, i.class_position, i.section_limit, i.score,
         i.eligibility_rank, v.view, v.feedback_status, v.rejected_reason,
         v.bugged_reason, v.feedback_at,
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
),
filtered AS (
  SELECT * FROM base
  WHERE CASE :filter
          WHEN 'fresh_new' THEN fresh = 1 AND feedback_status = 'new'
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
SELECT vacancy_id, class, score, eligibility_rank, fresh, view, feedback_status,
       rejected_reason, bugged_reason, feedback_at
FROM ranked
WHERE feedback_status <> 'new' OR rank_in_class <= section_limit
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
)
SELECT COALESCE(SUM(fresh = 1 AND feedback_status = 'new'), 0) AS fresh_new,
       COUNT(*)                                                AS "all",
       COALESCE(SUM(fresh = 1), 0)                             AS fresh,
       COALESCE(SUM(feedback_status = 'applied'), 0)           AS applied,
       COALESCE(SUM(feedback_status = 'rejected'), 0)          AS rejected,
       COALESCE(SUM(feedback_status = 'bugged'), 0)            AS bugged
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
)
SELECT class, COUNT(*) AS total
FROM base
WHERE CASE :filter
        WHEN 'fresh_new' THEN fresh = 1 AND feedback_status = 'new'
        WHEN 'all'       THEN 1
        WHEN 'fresh'     THEN fresh = 1
        ELSE feedback_status = :filter
      END
GROUP BY class;

-- name: pipeline_running
-- The latest run still marked running. Whether it is really alive is decided
-- by the reader from heartbeat_at (and the pid, on the same host).
SELECT id, started_at, heartbeat_at, stage, pid, host
FROM pipeline_runs
WHERE status = 'running'
ORDER BY id DESC
LIMIT 1;

-- name: set_feedback
UPDATE vacancies
SET feedback_status = :status,
    rejected_reason = :rejected_reason,
    bugged_reason = :bugged_reason,
    feedback_at = :at,
    feedback_selection_id = :selection_id
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
