# 0048 A source or company that disappears keeps its choice

Source: the agent, 2026-10-20, while making categories stable

## Business
Sources and company names come and go, so their rows hide when nothing is
left in them. When a hidden row comes back after the next collection, it is
not clear whether the person's earlier choice (shown or hidden) comes back
with it, or the row returns in its default state.

## Implementation
Check what the stored filter keeps for a value that is not listed, and make
it keep the choice.

## Items
- DONE - Checked 2026-10-21. Company: keeps the choice (a hidden name the view empties stays on the list, unticked). Source: lost it. The view keeps the boards shown, and every listed board ticked became "all"; so with devitjobs hidden and emptied by "Hot leads", linkedin off and on again made the filter "all", and devitjobs came back ticked
- DONE - Fix: every listed board ticked becomes "all" only when no board seen since the app started is off the list; the "All" row itself is "all" as before. UI test, failing without the fix
