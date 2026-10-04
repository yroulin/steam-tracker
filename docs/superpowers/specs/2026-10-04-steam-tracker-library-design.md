# Steam Tracker Library Design

## Goal

Make the existing Steam tracker a reliable, attractive library tool for several
owned accounts and Steam Families. The interface should work well on phones and
desktop, make ownership easy to understand, and distinguish dates Steam reports
from dates the tracker observes locally.

## Current state

- Python 3.10+ fetches owned libraries, Steam Families data, and optional store
  metadata. It writes `steam_games.json`, Markdown, and a self-contained HTML page.
- The HTML page currently presents a wide sortable table. At phone widths it
  remains a table, while the controls wrap into a large sticky toolbar.
- Steam Families provides `rt_time_acquired` for shared games. The owned-library
  API does not provide a general purchase date.
- The checked-in JSON predates schema version 2 and mixes family and owned
  semantics. It must be replaced only by a real successful update, not manually
  rewritten to fit the new interface.
- `accounts.json` contains credentials and must never be read into generated
  public artifacts or displayed in diagnostics.

## Proposed approach

Keep Python as the data and update layer, and keep the static HTML output so the
library remains easy to open and deploy through GitHub Pages. Add a local,
versioned first-seen history file maintained by `update.py`. Each successful
update carries forward the earliest observed date per app ID and adds newly
observed games using the update's UTC date. The tracker date is separate from
Steam Families' `acquired` date; neither is presented as a purchase date for
owned games. Existing data without a history file is initialized on the first
real update, so initial dates are explicitly labeled as first tracked dates and
not backfilled purchase dates.

Redesign the static frontend as a mixed dashboard and library:

- Compact summary metrics and a clear updated-at/source indicator.
- Search and the most useful filters remain easy to reach; secondary filters
  collapse into a mobile-friendly disclosure.
- Desktop retains a scannable sortable table; mobile uses stacked game cards
  with title, owned accounts/family owners, playtime, and relevant dates.
- Ownership is explicitly separated into owned accounts and family sharing.
- Dates have precise labels: “Visto por primera vez” from local history and
  “Adquirido (familia)” only where Steam provides it.
- Visual system uses restrained Steam-inspired dark neutrals and blue accents,
  consistent spacing and type scale, clear focus indicators, and readable
  contrast. Avoid skewed/slanted styling and decorative motion that harms
  legibility.
- Support keyboard navigation, semantic controls, visible focus, reduced-motion
  preferences, and touch targets appropriate for phones.

## Data and behavior

- Add a history file, proposed name `steam_history.json`, ignored from public
  publishing and versioned by schema. It stores only app IDs and first-seen UTC
  dates; no credentials or account tokens.
- `update.py` loads the prior history, merges dates for apps still present, and
  records newly observed app IDs. Preserve dates when the update succeeds; failed
  fetches must leave existing outputs and history intact.
- `publish()` exposes `first_seen` on game records in generated output, while
  the history source remains a local tracker file. The public date indicates
  when this tracker first saw the game, not when Steam says it was purchased.
- Rebuilding HTML from existing JSON must remain read-only with respect to
  history and must continue to work offline without credentials.
- CSV export and sorting should include the new date and keep existing fields.
- Keep legacy-schema rendering defensive, but do not infer missing ownership or
  first-seen data for old records.

## Scope

Included: first-seen tracking, Python update integration, responsive redesign,
clearer ownership/date semantics, accessible interactions, and documentation.

Not included: a server framework, user authentication, editing Steam data,
historical purchase prices, or claiming purchase dates the Steam APIs do not
provide.

## Validation

- Unit tests cover history initialization, carry-forward, newly observed games,
  failed-update preservation, and secret-free generated output.
- Run the project test suite and generate the HTML from a fixture.
- Inspect the rendered page at narrow mobile and desktop widths, and check
  keyboard focus, reduced-motion behavior, and representative empty/legacy data.

## Risks and decisions

- The first-seen date can only be accurate from the first successful update that
  creates local history. Existing library entries cannot be backdated reliably.
- The current legacy JSON may not reflect current ownership semantics; a real
  update is required for reliable account chips and family classification.
- GitHub Pages output is public in the current workflow. The local history file
  should not be copied into `_site`; only the intended `first_seen` field in the
  sanitized public library output is published.
