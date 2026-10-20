# 0061 A task scheduler: collections and clean-ups on a schedule

Source: the owner, 2026-10-21 ("since we are making a backend service, we can
control when new tasks start: a 'Task scheduler' item in the menu, a popup
that registers tasks in cron; the tasks are the ones shown in the task list")
Scope: app, tools

## Business
Collections are started by hand today. With the task service (0056) the
owner can tell it when: "collect for every identity at 07:00", "a clean-up
every Sunday". What a schedule starts is an ordinary task of the queue: it
appears in the bottom panel, runs, and ends as any other.

What can be scheduled:
- collect vacancies for one, several or all active identities (the whole
  group: top, LinkedIn, the rest, CV/CL);
- LinkedIn only; the rest of the base only;
- a clean-up, with the filters of the "Clean up" dialog;
- a CV/CL batch;
- a re-check of the shortlist's links.

Per schedule the owner picks what happens to a run that was missed while
the laptop was off or asleep: catch up once, or skip it (the owner,
2026-10-21: an option of the schedule itself, both ways possible).

## Implementation
Schedules are rows in `data/tasks.sqlite` (0056): what, its parameters, a
cron expression, on/off, catch-up or skip, the last and next run. The
background worker adds the task when a schedule is due; a schedule whose
previous run is still queued or running is skipped, with a line saying so.
The cron expression is parsed in Python (a small parser of our own or
`croniter`).

The app: a "Task scheduler…" item in the menu, a popup listing the
schedules (on/off, next run, last result) and a form to add or change one:
the kind, its parameters (identities, clean-up filters), the time as presets
(every day at HH:MM, every N hours, days of the week) or a raw cron line,
with the next three runs shown before saving.

Waking the laptop for a schedule (Task Scheduler wake timers) is not part
of this task.

## Items
- DONE - Plan (2026-10-21, with the owner)
- TO DO - Schedules in the queue's file; cron parsing; due, skip-while-running, catch-up or skip; tests with a fake clock
- TO DO - `tools/taskq.py schedule add/list/remove` for the agent
- TO DO - "Task scheduler…" popup: list, add, edit, on/off, next runs; UI tests
- TO DO - End-to-end: a schedule adds its task, the task runs and ends, the schedule shows the result
