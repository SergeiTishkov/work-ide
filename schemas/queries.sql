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
-- LIMIT. Vacancies without feedback are capped at section_limit per class,
-- ranked AFTER the filter, so "fresh without feedback" shows the top of the
-- fresh ones. Vacancies with feedback are never capped: there are few, and
-- hiding one a person has marked would make the mark look lost.

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
ORDER BY class_position, score DESC, eligibility_rank, vacancy_id;

-- name: listing_counts
WITH baseline AS (
  SELECT MAX(id) AS id FROM selections WHERE kind = 'run' AND id <= :selection_id
),
base AS (
  SELECT i.class, i.section_limit, v.feedback_status,
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
),
per_class AS (
  SELECT class, section_limit,
         SUM(feedback_status = 'new')              AS new_n,
         SUM(feedback_status = 'new' AND fresh = 1) AS fresh_new_n
  FROM base GROUP BY class, section_limit
),
capped AS (
  SELECT SUM(MIN(section_limit, new_n))       AS new_shown,
         SUM(MIN(section_limit, fresh_new_n)) AS fresh_new_shown
  FROM per_class
),
marked AS (
  SELECT SUM(feedback_status <> 'new')              AS all_marked,
         SUM(feedback_status <> 'new' AND fresh = 1) AS fresh_marked,
         SUM(feedback_status = 'applied')           AS applied,
         SUM(feedback_status = 'rejected')          AS rejected,
         SUM(feedback_status = 'bugged')            AS bugged
  FROM base
)
SELECT COALESCE(capped.fresh_new_shown, 0)                                   AS fresh_new,
       COALESCE(capped.new_shown, 0) + COALESCE(marked.all_marked, 0)        AS "all",
       COALESCE(capped.fresh_new_shown, 0) + COALESCE(marked.fresh_marked, 0) AS fresh,
       COALESCE(marked.applied, 0)                                           AS applied,
       COALESCE(marked.rejected, 0)                                          AS rejected,
       COALESCE(marked.bugged, 0)                                            AS bugged
FROM capped, marked;

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
