# 0056 A collection keeps going when another Windows user is active, and through sleep where it can

Source: the owner, 2026-10-20 ("when the active Windows user changes, my
long-running collection scripts started under the first user stop working;
make them able to work while another user is active, or even while the
system sleeps, if that is possible at all")
Scope: app, tools

## Business
The owner starts a collection, then another person signs in to the same
laptop with Fast User Switching. The collection started under the owner
stops. A collection takes hours (the LinkedIn walk alone six hours and more,
task 0050), so a switch in the middle loses most of a run.

What is known so far, checked 2026-10-20 on the owner's laptop:
- Windows does not pause the processes of a session that was switched
  away from: they keep their CPU time. Something in the chain stops for
  another reason, and nobody has seen the logs of a run that stopped yet.
- The chain is not "background scripts only": the Electron app's task
  queue (`app/main/tasks.js`) starts every collection. It spawns
  `claude -p /top <p>` (`app/main/runner.js`), which runs the Python
  pipeline; LinkedIn, the rest of the base and reputation are separate
  lanes of the same queue. The queue lives in the app's memory.
- The laptop has S3 sleep (no Modern Standby). Plugged in it never sleeps
  (Balanced plan); on battery it sleeps after 30 minutes without input,
  and a switch to the sign-in screen with nobody touching it counts as no
  input. In S3 no process runs at all: "working while asleep" can only
  mean not letting the laptop fall asleep during a run, waking it up for a
  run, or carrying on after waking.

## Implementation
Not decided; the cause comes first. Candidates, to be weighed against
what the logs show:
- The run does not depend on the app's session: a standalone runner
  started by Task Scheduler with "Run whether user is logged on or not",
  reading the queue from the base; the app shows and controls it instead
  of being its parent. Word documents (the `documents` lane, Word COM)
  need a signed-in desktop and stay in the app.
- Chromium throttling in a disconnected session, if the app's own timers
  (queue retries, log followers) turn out to be the part that stops:
  `powerSaveBlocker`, background-throttling switches.
- Windows 11 power throttling (EcoQoS) of background processes, if the run
  slows down rather than stops: `powercfg /powerthrottling disable` for
  python.exe and claude, or a process-level opt-out.
- Sleep: keep the system awake while a task runs
  (`SetThreadExecutionState` / `powerSaveBlocker('prevent-app-suspension')`);
  a scheduled collection may wake the laptop ("Wake the computer to run
  this task" and wake timers in the power plan); a run cut by sleep resumes
  from its last finished stage rather than from the start.

## Items
- TO DO - Reproduce: start a collection, switch user, come back; record which process stopped (app, the `claude -p` agent, python, a fetcher), when, and what the run logs in `data/identities/<p>/runs/` say
- TO DO - The same with the laptop on battery, past the 30-minute sleep
- TO DO - Work out the plan from what was found and write it here as the next items
