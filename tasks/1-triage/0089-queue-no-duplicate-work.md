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

## Implementation
To be decided with the owner. Proposals:
- One rule for "the same work is going": a collection of the identity is
  going while ANY task of its group is queued or going; a click or a
  schedule then queues nothing and says "already going: #11 LinkedIn, 80%".
  The same for a single kind (`rest`, `linkedin`, `cv_batch`) against a
  group that holds it.
- Schedules: skip a due run when the same work for the identity is going,
  whoever started it (the rule above), not only the schedule's own run.
- Optional: a schedule's minimum gap: a run due less than N hours after the
  previous run of the same work ENDED is skipped (a 23:00 catch-up that
  ended at 00:50 makes the 01:00 run pointless). N per schedule, or a
  default such as half the period.
- The worker ends between tasks when its code changed (as the app's
  code stamp does), so a fix applies without closing anything.
- On reliability without a server: the queue is local by design; what made
  it miss work was no worker running (0056: `taskd.py install`, a worker of
  the user's session started by Task Scheduler, outside the app), a session
  that ended before its pipeline (0088), and races between the batch and
  the person (0087). A server is not needed for any of these.

## Items
- TO DO - Decide with the owner: the "same work is going" rule, the minimum gap, the worker restart on new code
