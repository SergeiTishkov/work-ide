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
- TO DO - Check the behaviour on a source that vanishes and returns; write the fix here if it loses the choice
