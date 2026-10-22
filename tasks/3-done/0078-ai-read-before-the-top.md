# 0078 Nothing reaches the top before the AI read

Source: the owner, 2026-10-22 (40 vacancies in the selection, office jobs as remote)
Scope: tools, app, docs

## Business
The owner opened the app on 2026-10-22 and found 40 new vacancies, five
times a usual week. Most were office jobs with remote work on some days
"if the manager agrees". The owner took them for the night's scheduled
collection and asked:
- does the AI processing of vacancies start at all;
- did a process stop and not start again;
- a fifth class, "Not processed with AI", between the long shots and
  "remote not confirmed": whatever the scrapers and the scripts say about
  remote, a vacancy waits there for the cheap model's positive read, then
  moves up or down;
- the AI step must not fail as a whole without a restart.
The owner will sort the 40 by hand; they are not to be sent to AI now.

What happened (2026-10-22):
- No collection ran that night. The schedule "0 1 * * *" exists in
  `data/tasks.sqlite`, never ran (`last_run_at` empty): the task service is
  not installed on this machine (task 0056 waits for the owner's
  `taskd.py install`). No pipeline run after 2026-10-21 19:42.
- The 40 came from selection #49, 01:22 that night: the agent's one-off
  repair for task 0076 rescored the whole base with the current criteria
  and recorded a "rebuild" selection without the AI step. The criteria had
  changed since the last run: the ITAR fix of task 0073 freed vacancies
  refused for "itar" inside "military" (in the US equal-opportunity
  boilerplate). 39 vacancies entered the list (12 hot_lead, 15
  worth_a_look, 11 long_shot, 1 remote_unconfirmed), 37 of them with
  "military" in the text; none had been read by the AI check.
- The AI check itself worked in every logged run: 2026-10-20 18:03 (86
  read, 83 rejected), 22:16 (47, 39), 2026-10-21 19:14 (114, 112).
- The flaw: the scripts' verdict alone put a vacancy in the top classes;
  only a pipeline run's AI stage took it out. Any rescore outside that
  stage, or a run whose AI stage failed, showed unread vacancies as the
  top.

## Implementation
- `score.py`: a vacancy the scripts put in a top class
  (`ai_screen.TOP_CLASSES`) with no AI answer for its current text gets
  the class `ai_unscreened`; the scripts' class stays in
  `computed.script_class`. "keep" moves it there, "reject" out. Off per
  identity with `ai_screen: {required: false}`.
- The class is listed (`report.LISTED_CLASSES`) between long_shot and
  remote_unconfirmed, read by the AI check (`ai_screen.SCREENED_CLASSES`),
  its description fetched (`enrich_descriptions.HEAD_CLASSES`), offered by
  the clean-up; the app shows "⏳ Not processed with AI" / "⏳ Не обработано
  AI". CVs, channels and company facts are not made for it.
- `ai_screen.screen`: a failed call is sent again, two more rounds after
  20 s.
- `pipeline.queue_ai_read`: a run that saves with vacancies waiting queues
  the task `ai` (`pipeline.py --ai`, once per identity); at the usage limit
  the queue reruns the run itself. An `ai` run that leaves vacancies
  waiting exits 1. Every later run reads them as well.
- `docs/ARCHITECTURE.md`: "Nothing reaches the top before the AI read".

## Items
- DONE - Found the cause of the 40 (no night run; the 0076 repair's rescore without the AI step)
- DONE - The class `ai_unscreened`, in the scoring, the lists and the app
- DONE - Failed calls sent again; a run that leaves vacancies unread queues the AI check
- DONE - The base rescored with the rule, a rebuild selection recorded (no AI calls, at the owner's word)

## Applied to the base (2026-10-22)
Rescored with the rule, no AI call, a "rebuild" selection recorded:
- sharp: 38 moved to `ai_unscreened` (12 hot_lead, 15 worth_a_look,
  11 long_shot); selection #51.
- partsharp: 60 moved to `ai_unscreened` (52 engagement_unconfirmed,
  4 long_shot, 3 hot_lead, 1 worth_a_look); selection #52.
The next run, or the queued `ai` task, reads them.
