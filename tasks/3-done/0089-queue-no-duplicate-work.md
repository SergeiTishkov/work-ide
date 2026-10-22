# 0089 Work already going is not queued again

Source: the owner, 2026-10-23
Scope: tools, app

## Business
The owner, 2026-10-23: work that is going now must not be started again.
Example: the daily schedule ran late (at 23:00, the computer slept at its
time) and is still going at 01:00, when the next run is due: that run should
not start. This is about schedules. The owner also finds the processing
unreliable as a whole, and notes there is no server.

What happened, 2026-10-22/23 (schedule #1, `0 1 * * *`, collect sharp,
`missed: catch_up`):
- 01:00 on 10-22: no worker was up (the app closed, `taskd.py install` not
  done, task 0056), so nothing ran.
- 20:12: the app opened, its worker caught the run up: tasks 10-15.
- 01:00 on 10-23: LinkedIn #11 still going (5.5 hours, 80%); the schedule
  wrote "skipped, the previous run is still running" and queued nothing.

What is covered now:
- a schedule whose previous run is queued or going skips its next run
  (`schedules.run_due`, the schedule's own last tasks);
- a collection of an identity whose top (`collect`) is queued or going is
  not queued twice (`taskq.collection`);
- one task of the same kind, identity and vacancy at a time (`taskq.add`).

Gaps found:
- `taskq.collection` checks the top task only. On 10-23 the top (#10) was
  done while LinkedIn #11, the rest #12 and two CV/CL batches waited: a
  "Collect" in the app, or another schedule for the same identity, would
  queue a second group, with a second rest and more batches. Only LinkedIn
  is checked on its own.
- Two schedules (or a schedule and a click) for the same identity know only
  their own tasks.
- A run caught up late and ended at 00:50 is followed by a full run at
  01:00: a second collection ten minutes after the first.
- The worker keeps the code it started with: the app's worker of 20:12
  still runs the code before tasks 0087 and 0088.

The owner's decision, 2026-10-23: the "same work is going" rule, for the
whole collection: "a collection is in fact a batch of tasks; count the
whole batch". The minimum gap and the worker restart on new code are not
taken now.

## Implementation
- `tools/taskq.py`: `active_collection()`: a queued or running task of the
  identity that is its top (`collect`) or belongs to a collection's group
  (LinkedIn, the rest, a CV/CL batch), the running one first.
  `collection()` queues nothing while it finds one, and returns it.
- `tools/schedules.py`: the note of a run that queued nothing names what is
  going: "nothing queued, the same work is going: #11 linkedin sharp
  (running)".
- The app: "Collect vacancies" is off while a task of the identity's
  collection runs or waits after its top, with "Collection going: <task>".
- Single kinds were covered already: `taskq.add` queues one task of a kind,
  identity and vacancy at a time, a task of a group included.
- Tests: `test_taskq.py`, `test_schedules.py`, `app/test/ui/app.spec.js`.

Proposed, not taken (the owner, 2026-10-23): a minimum gap between runs of a
schedule (a catch-up that ended at 00:50 and the run due at 01:00); a worker
that ends between tasks when its code changed.

## Items
- DONE - A collection is going until the last task of its group ends; none is queued beside it
- DONE - A schedule's note names the work that is going
- DONE - The app shows the collection as going while its group runs
