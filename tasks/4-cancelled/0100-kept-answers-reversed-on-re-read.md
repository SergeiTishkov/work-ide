# 0100 Kept answers read again come back "reject" for a quarter of the list

Source: task 0084's measurement, 2026-10-25: sharp
Cancelled: the owner, 2026-10-28: the list is kept empty and applied to at once, so a re-read only touches vacancies already seen; and since task 0103 a prompt change reads nothing again unless the owner asks for it
Scope: tools

## Business
A change of the screening prompt sends every "keep" answer to the model
again (the brief hash changes). After task 0084, 121 kept vacancies in the
list were read again: 89 kept, 2 refused for language (the Scalo pair, the
change's purpose), 30 refused on other grounds: location or time zone 20, stack or
level 7, part time 1, not a single job 1, AI training 1. Among them:
- Enode f6fafcf3: "specific location eligibility ('Europe') are not clearly
  stated";
- Proxify d03dce24: "person at UTC+4 is inside the window per the checker,
  but ... unable to consider applications from candidates in other time
  zones";
- GRASWALD AI 9637561c: "names Germany as the location and does not
  explicitly state it hires outside Germany".
CV and letter were made for four of the thirty on the same day (cv_batch
#26: infraMOD, Enode, GRASWALD AI, Crossing Hurdles). The same text and
the same CV gave "keep" before; only the prompt's language part changed.

## Implementation
For the owner to choose:
- a prompt change that only adds a reason to refuse keeps a "keep" answer
  and asks only that reason (a narrower question);
- a "reject" that reverses a "keep" is asked a second time, and the
  vacancy leaves only on two;
- nothing changes; a re-read is a fresh opinion.

## Items
- TO DO - The owner chooses
