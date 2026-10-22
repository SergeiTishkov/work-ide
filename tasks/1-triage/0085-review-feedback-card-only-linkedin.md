# 0085 LinkedIn cards with no description in remote not confirmed

Source: feedback review, 2026-10-22: sharp, vacancies 633b25ec, 0a0e04ed, 365ebd17, 5cf245c6, 8254e4da, 61f37b9c, 91f16407
Scope: tools

## Business
The person marked seven LinkedIn vacancies in "Remote not confirmed" as
wrong picks, with no reason. All seven are cards from selection #39 with
next to no text: descriptions of 0 to 588 characters; four never had a
description fetch (`description_fetch` empty), one fetched 0 characters.
Locations: Berkeley Heights NJ, Irvine CA ("Dotnet Developer (US Citizen)"),
West Berkshire, London, Montrouge, Alpharetta GA, Singapore. The class
exists so a person checks what the employer never called remote; with no
text there is nothing to check but the title and the city.

## Implementation
For the owner to choose:
- `enrich_descriptions` fetches remote_unconfirmed cards first (the class is
  in HEAD_CLASSES, but these were never reached);
- after the fetch, the AI check reads remote_unconfirmed as it reads
  ai_unscreened (0078): "remote" confirmed moves it up, "onsite", "hybrid"
  or a location limit moves it out;
- a LinkedIn card with no description after N fetch attempts leaves the
  list.

## Items
- TO DO - The owner chooses the treatment
- TO DO - The change, with a test on a card-only record
