# Bindung — Plan

As of 2026-11-10. Agreed in a requirements interview and written by Fable 5.1
for review; the work packages are built by cheaper models (Sonnet 5.5) wherever
possible. This plan is the binding
spec. Code, UI, templates and `CLAUDE.md` are German, like finctl and health;
the plan is English so it is easy to review. A changed decision is changed
here in the same step.

## 1. Goal

Bindung helps one person stay in touch with the people who matter, privately
and professionally: former colleagues, mentors, friends, family. It remembers
**what you last talked about**, so the next call can pick up where the last one
ended, and it **prompts you before a bond goes cold**.

Reminder-first, memory close behind: the home view shows who is due; the note
is what you read before you reach out.

What a good week looks like: a daily digest only when someone is due, and a
ten-minute weekly review of "Diese Woche" where you read the last notes and
decide whom to call.

## 2. Fixed rules

Taken over from finctl and health, adjusted for a server that will later be
reachable from the internet.

- **Data stays on the user's own server.** Nothing is sent anywhere except the
  web-push message to the browser's push service, and that carries only the
  digest text.
- **No AI at runtime.** Due dates, digests and calendar entries come from
  explicit rules. AI writes code.
- **No real people in the repository.** No real names, companies, phone
  numbers or notes in code, tests, templates or screenshots. Test data is
  invented. The repository is public.
- **One path root:** `bindung/pfade.py` → `~/Library/Application Support/Bindung`
  on a Mac, `BINDUNG_DATEN` overrides it (in a container: a mounted volume). No
  module builds its own paths; `tests/test_pfade.py` keeps the count at zero.
- **Container-ready from day one:** bind host `BINDUNG_HOST` (default
  `127.0.0.1`), port `BINDUNG_PORT` (default `8785`), `BINDUNG_SICHER=1` marks
  that a TLS proxy sits in front (cookies become `Secure`). No Docker image in
  v1, but nothing in the code may assume a Mac.
- **Times in UTC in the database, days as ISO dates in the user's time zone**
  (default `Europe/Berlin`, a per-user setting).
- **pytest green and ruff at zero findings before every commit.** Browser
  tests with Playwright run alone, like in finctl.
- **Release notes:** every tag gets a section in `CHANGELOG.md` written for the
  people who use the app, before tagging.
- **PLAN.md is the spec, CONTEXT.md is the vocabulary.** Code uses the words
  from CONTEXT.md and nothing else for the same thing.

## 3. Stack

Python 3.12 · SQLite via stdlib `sqlite3`, `schema.sql` plus numbered
migrations (`db.MIGRATIONEN`, pattern from health) · Typer CLI `bindung` ·
FastAPI + Jinja2, server-rendered, HTMX for partial updates (panes, list rows,
forms), a little plain JS for dictation, push registration and keyboard
behaviour · no CSS framework, one hand-written stylesheet · pytest + ruff with
finctl's rule selection · `.claude/launch.json` with `bindung serve`.

Dependencies beyond finctl's set: **`pywebpush`** (web push with VAPID). The
calendar file is written by hand (RFC 5545 is small); no `icalendar` dependency.

**Mac app** (WP7, pattern from health): `werkzeuge/paket/bauen.sh` builds
`dist/Bindung-<version>-mac.dmg` with PyInstaller. Double-click starts
`bindung/starter.py` (also `bindung app`): server on `127.0.0.1:8788`,
menu-bar icon (`bindung/menueleiste.py`), no Dock icon, opens the browser,
daily task inside. Matters more here than in finctl: push digests and the
calendar feed only work while the server runs.

## 4. Users and login

- Each user's data is private. Every table that holds user data carries
  `nutzer_id`; every query filters by it; there is no cross-user view.
- No self-signup. The CLI creates and resets users:
  `bindung nutzer anlegen <name>` (asks for the password twice),
  `bindung nutzer passwort <name>`, `bindung nutzer liste`.
- Passwords are hashed with stdlib `hashlib.scrypt` and a per-user salt.
- Login sets a session cookie: random token in a `sitzung` table with expiry
  (30 days, renewed on use). `HttpOnly`, `SameSite=Lax`, `Secure` when
  `BINDUNG_SICHER=1`. Logout deletes the row. Failed logins get a growing delay
  per user name.
- The calendar feed is the one route without login; it is protected by a
  per-user secret in the URL (§9).
- **Settings page** (`/einstellungen`): change password, digest time, default
  interval, default lead time, time zone, calendar feed URL (with "neu
  erzeugen"), push on/off, dictation language, appearance (System / Hell /
  Dunkel).

## 5. Domain model

Vocabulary is in CONTEXT.md. Tables (all with `nutzer_id` where user data):

| Table | Holds |
|---|---|
| `nutzer` | name, password hash, digest time (default 08:00), time zone, default interval days (56), default lead days (7), calendar token, dictation language, appearance (`darstellung`: `system`, `hell`, `dunkel`; default `system`) |
| `sitzung` | login sessions |
| `person` | name, company, job role, phone, email, city, how we met, profile note, interval days (NULL → user default), next-date override (NULL → from interval), archived-at |
| `tag` | user-defined tag names, order |
| `person_tag` | n:m |
| `kontakt` | per person: date, kind (`anruf`, `nachricht`, `email`, `treffen`, `sonstiges`, `schaetzung`), note |
| `angehoeriger` | family entry on a person: name, role (`partner`, `kind`, `elternteil`, `geschwister`, `sonstiges` + free text), birthday, linked person (NULL), counterpart id (NULL) |
| `stichtag` | per person: label, kind (`geburtstag`, `jahrestag`, `sonstiges`), month-day with optional year, lead days (NULL → default), optional family entry it belongs to |
| `push_abo` | web-push subscriptions per user (endpoint, keys) |
| `digest_protokoll` | per user: the day the last digest was sent |
| `schema_version` | migrations |

Rules the model enforces:

- A person has **any number of tags**. Tags are user-defined; the sidebar shows
  one list per tag. Deleting a tag only detaches it.
- **Archive, never delete** a person from the UI. Archived people leave every
  list and card, keep their history, and have a restore button under "Archiv".
  Deleting is a CLI command, if ever.
- **Family link symmetry.** Linking a family entry to another person in the app
  creates the counterpart entry on that person with the inverse role (partner ↔
  partner, kind ↔ elternteil, geschwister ↔ geschwister, sonstiges ↔ sonstiges),
  both rows pointing at each other. The inverse role is editable on its side.
  Unlinking or deleting one side removes the counterpart. A family entry without
  a link is plain text plus optional birthday.
- A birthday on a family entry is stored as a Stichtag of the person, tied to
  the family entry, so a child's birthday shows up for the parent.
- A **rough last contact** ("diesen Monat", "vor ein paar Monaten", "über ein
  Jahr her", "unbekannt") is stored as a Kontakt of kind `schaetzung` with an
  approximate date (today −15, −90, −400 days) and no note, so the due logic
  needs no special case. "unbekannt" stores nothing.

## 6. Due logic

For a person on day `heute` in the user's time zone:

- `letzter_kontakt` = latest Kontakt date, or none.
- `intervall` = person's interval or the user default (56 days).
- `faellig_am` = next-date override if set, else `letzter_kontakt + intervall`.
- **Zustand** (state), exactly one:
  - `unbekannt`: no Kontakt at all. Never due, never counted on a card. Shown
    with a grey "noch kein Touchpoint" label in the list and in a sidebar filter.
  - `erkaltet`: `heute − letzter_kontakt > min(2 × intervall, 180)` days.
  - `ueberfaellig`: `heute > faellig_am` and not erkaltet.
  - `bald`: `faellig_am` within the next 7 days.
  - `ok`: everything else.
- Logging a Kontakt clears the next-date override. The next due date follows
  from the new latest contact.
- A **Stichtag** surfaces from `vorlauf` days before it (default 7, per date
  overridable) until the day itself. It does not change the person's state; it
  is listed on the person row as a badge and counts for the week card.

**Cards** (top of the middle column, click filters the list):

1. **Braucht Aufmerksamkeit** — people with state `ueberfaellig` or `erkaltet`.
2. **Erkaltet** — people with state `erkaltet` (a subset of card 1, sorted to
   the top there too).
3. **Diese Woche** — people with state `bald` plus people with a Stichtag in
   its lead window, deduplicated.

Sort order in filtered lists: erkaltet first, then by `faellig_am` ascending,
then name. Default list ("Alle"): by name, with the state as a coloured dot.

## 7. Screens

Three panes like Apple Reminders on macOS, muted palette, system font, no
decoration. One page; HTMX swaps panes.

- **Left sidebar:** Alle, Noch kein Touchpoint, Archiv; then one entry per tag
  with its count; "Tag hinzufügen" at the bottom; user name and Einstellungen
  at the very bottom.
- **Middle column:** the three cards with counts; a search field (name,
  company, city, tag; filters as you type); "Person hinzufügen" and
  "Mehrere hinzufügen"; the list. A row shows a checkbox-style circle, name,
  company, the first line of the latest note, and on the right the state badge
  ("vor 3 Wochen", "überfällig seit 12 Tagen", "Geburtstag in 4 Tagen").
  Clicking the circle opens **Touchpoint eintragen** for that person. Clicking the
  row selects it.
- **Right pane:** the person, top to bottom: header with name, company and
  role, tags as chips, phone (tel: link) and email (mailto: link), city, how we
  met, profile note (with a one-line hint that it saves when the field is left).
  A prominent **Touchpoint eintragen** button. Then: Zuletzt besprochen
  (the history, latest first, each with date, kind and note), Angehörige,
  Stichtage, Intervall and next date, Archivieren. Everything edits inline.
- **Touchpoint eintragen** (sheet over the right pane): kind as a segmented
  control, date (default today), note with a mic button, Save. Saving adds the
  entry, updates the row and the cards without a page reload.
- **Mehrere hinzufügen** (sheet): a text area, one name per line, optional
  "Name; Firma" per line, a tag picker, and a rough last contact for the batch.
  Creates all persons, selects the first.
- **Einstellungen**: §4.
- **Anmeldung**: one form, like finctl.

**Responsive:** below 768 px the three panes become a stack with navigation:
sidebar → list → person, with a back arrow. Touch targets ≥ 44 px. A
`manifest.webmanifest` and icons make it installable on iPhone and in the Dock.
No offline mode in v1; the service worker exists for push only.

**Design conventions** live in `docs/design_conventions.yaml` (pattern from
finctl) and `tests/test_design.py` checks what it can: colours only from the
palette, no inline styles, every form field has a label, German strings only
in templates.

## 8. Dictation

A mic button next to every multi-line text field (notes) and the quick-add
area. v1 uses the browser's built-in recognition (`SpeechRecognition` /
`webkitSpeechRecognition`), which uses the device microphone and Apple's
recogniser in Safari on Mac and iPhone. The language (de-DE / en-US) is a user
setting (Einstellungen › Diktat; the toggle on the button was dropped in WP6,
see section 13).

The button talks to one small JS interface (`diktat.js`: `starten(feld)`,
`stoppen()`, `verfuegbar()`), so a later server-side transcriber (record with
`MediaRecorder`, POST the audio, run Parakeet v3 in a sidecar container) can
replace the backend without touching templates. Browsers without recognition
hide the button.

## 9. Calendar

- **Feed:** `GET /kalender/<token>.ics`, no login, `token` is a 32-byte secret
  per user, regenerable in settings (which invalidates the old URL). The
  settings page shows the `webcal://` link and a copy button.
- **Download:** the same content from the settings page with
  `Content-Disposition: attachment`.
- **Content:** one yearly `VEVENT` per Stichtag (with the age or years when
  the year is known, e.g. "Anna Beispiel wird 40"), and one all-day `VEVENT`
  per non-archived person with a due date ("Melden bei Anna Beispiel") at
  `faellig_am`, with a `VALARM` the morning of; overdue and cold people on the
  next Sunday (the weekly review), not on every new day. People with state `unbekannt`
  are not in the feed. Stable `UID`s per person and per Stichtag, so Calendar
  updates rather than duplicates.

## 10. Notifications

- **Web push.** The service worker (`sw.js`) subscribes with VAPID keys that the
  server generates on first start and stores in the data folder
  (`vapid.json`). The subscription is stored in `push_abo`. Settings and a
  one-time banner on the home view ask for permission; the banner explains that
  Safari on the Mac needs the app in the Dock first.
- **Daily digest.** A background task inside the server process runs every
  minute. For each user whose digest time has passed today (user's time zone)
  and whose `digest_protokoll` shows no digest today, it computes the cards.
  If card 1 or card 3 has anything **due today or overdue**, it sends one
  push: "3 Personen warten · 1 Geburtstag" with the first few names; clicking
  opens the app on card 1. Nothing due → no push. A dead subscription
  (410/404) is deleted.
- **Fallback banner.** When push is not granted or not available, the home
  view shows the same digest text as a dismissible banner once per day.
- Not in v1: email, per-person pushes, actions inside the notification.

## 11. Data folder and CLI

```
~/Library/Application Support/Bindung/     (BINDUNG_DATEN)
  bindung.db                               SQLite
  vapid.json                               push keys, generated on first start
  sicherung/                               `bindung sichern` writes dated JSON
```

CLI: `bindung serve [--host --port --reload]`, `bindung app` (menu-bar
starter), `bindung nutzer …` (§4), `bindung ort` (prints the data folder and
why), `bindung sichern` (JSON export of one user's data: persons, tags,
contacts, family, dates — the re-import is `bindung wiederherstellen`).

## 12. Work packages

Each WP ends with tests green, ruff clean, a CHANGELOG entry under
"Unveröffentlicht", and a short note in `docs/` if a decision was made.

- **WP0 Gerüst.** `pyproject.toml`, `pfade.py`, `db.py` + `schema.sql`,
  CLI `serve`/`ort`/`nutzer`, login and session middleware, base template with
  the three-pane skeleton and the palette, `design_conventions.yaml`,
  `tests/` with the throwaway data folder, lint test, `.claude/launch.json`.
  Done: `bindung nutzer anlegen`, log in, see an empty three-pane page.
- **WP1 Personen und Tags.** Person CRUD in the right pane, tags in the
  sidebar, search, archive and restore, "Mehrere hinzufügen" with rough last
  contact. Done: a list of invented people, filtered by tag and search, on Mac
  and at phone width.
- **WP2 Kontakte und Fälligkeit.** Touchpoint eintragen, history, due logic
  (§6), states, badges, the three cards with filtering, interval and next-date
  override per person. Done: the weekly review works.
- **WP3 Angehörige und Stichtage.** Family entries with linking and inverse,
  Stichtage with lead time, their badges and their part in card 3.
- **WP4 Kalender.** Feed and download (§9), settings page with the URL.
- **WP5 Benachrichtigungen.** Service worker, push subscription, VAPID,
  digest task, fallback banner, settings toggles (§10).
- **WP6 Diktat.** Mic button and `diktat.js` (§8), language setting.
- **WP7 Mac-App und PWA.** Manifest and icons, menu-bar starter, PyInstaller
  build and smoke test, first release `v0.1.0` with release notes.

Later, in this order, each as its own plan section when it comes:
Docker image and compose file with a TLS
proxy · server-side dictation (Parakeet v3 sidecar) · vCard import with a review
screen · sharing a person between users · email digest · Apple Contacts or
LinkedIn integration (not planned).

## 13. Decisions and their reasons

- **Web app, not native Mac.** Docker deployment, phone use and browser
  notifications only exist for a web app. "macOS first" means Mac browser
  layout first.
- **Tags, not one circle.** Colleagues become friends; a person keeps both.
- **History, not one overwritten note.** The point is to recall what someone
  told you; six months later the overwritten note is gone.
- **Cards, not only sidebar counts.** The user wants the three numbers in
  view, with a click to the filtered list.
- **No file import in v1.** There is no clean source (contacts are not in
  iCloud; Teams cannot export), and importing everyone works against choosing
  deliberately who matters. Quick-add covers the first sitting.
- **Unknown state instead of "due from day one".** Otherwise the cards show
  the whole list on day one and mean nothing.
- **Cold = min(2 × interval, 180 days).** Twice the interval for frequent
  people, a hard half-year ceiling for rare ones.
- **Lead time 7 days.** Matches the weekly review.
- **Push with a daily digest, not per-person pushes.** One quiet message a
  day, only when there is something to do.
- **Calendar feed and download.** The feed follows changes; the download is
  free once the feed exists.
- **Browser dictation first.** No model to install, works on iPhone, and the
  user's Handy app with Parakeet types into any field anyway. The interface
  leaves room for a server-side model.

Small decisions taken while building WP0, where the plan was silent:

- **Sessions store a hash, not the token.** `sitzung.token_hash` holds the
  SHA-256 of the cookie token, so a leaked database file does not hand out
  logins. The cookie is re-sent on every authenticated response so its
  30 days follow the renewed expiry in the database.
- **Failed-login delay lives in process memory**, per lower-cased user name
  (unknown names count too): 1, 2, 4 … up to 300 seconds, answered with
  `429`. A correct password during the delay is also refused. A restart
  clears it; there is no table for it. Revisit if the server ever runs with
  several worker processes.
- **Password minimum: 8 characters**, enforced in `auth.py` (CLI and later
  settings page).
- **Partial dates** (`angehoeriger.geburtstag`, `stichtag.datum`) are one text
  column in ISO 8601 form: `YYYY-MM-DD`, or `--MM-DD` without a year. One
  column instead of month/day/year keeps "optional year" a format question,
  not a schema one.
- **Extra column** `digest_protokoll.hinweis_weggeklickt_am`: the in-app
  Hinweis (§10) is dismissible once per day and needs a place to remember it;
  adding it now spares WP5 a migration. `nutzer.name` is unique ignoring case;
  `tag.name` is unique per user ignoring case.
- **Narrow screens in WP0 only stack** the three panes, sidebar first. The
  sidebar → list → person navigation with a back arrow (§7) comes with the
  person pane in WP1.
- **`/einstellungen`** is linked from the sidebar but the page itself belongs
  to WP4/WP5/WP6; until then the link ends on the server's 404.

Small decisions taken while building WP1, where the plan was silent:

- **View state lives in the URL**: `/?tag=3&filter=archiv&suche=anna&person=5`.
  The server writes it (`HX-Push-Url` when the user navigates, `HX-Replace-Url`
  while searching or saving), so reload and the back button show the same
  thing. Parts for HTMX (`/liste`, `/personen/<id>` ...) redirect to the full
  page when opened without HTMX. Mutations learn the open view from
  `HX-Current-URL`; a tag or person in it that is not the user's is dropped
  silently, while a foreign id in a path or in `GET /?tag=` / `?person=` is a 404.
- **Phone layout**: `data-ansicht` on `.app` (`seitenleiste`, `liste`, `person`)
  shows one column below 768 px. The page opens on the sidebar (as Apple
  Reminders does on the iPhone); the server tells the browser the column to show
  after every partial answer (`HX-Trigger: {"spalte": ...}`), the back arrows
  are plain `data-zeige` buttons in `bindung.js`.
- **Inline editing** is one form per person that posts on `change` and returns
  only out-of-band parts (status "Gespeichert", contact links, list rows); an
  invalid value answers 422 and replaces the page with the stored state plus the
  message. The form reads raw form data because FastAPI turns an empty optional
  form value into `None`, which would make clearing a field impossible.
- **Search and sorting happen in Python** (`casefold`), not in SQL: SQLite's
  `LIKE`/`NOCASE` only fold ASCII, and a search for "ärztin" must find "Ärztin".
  Tag names are unique per user by the same rule (`Ärzte` = `ärzte`). Lists are
  short enough (hundreds) for this to cost nothing.
- **Tag counts and archived people**: a tag's count and "Alle" count only active
  people; the archive has its own count. A search inside a list stays inside that
  list (tag or archive).
- **"Mehrere hinzufügen"** skips only names repeated inside the block, not names
  that already exist in the app; two different people may share a name. It also
  accepts one optional new tag name for the whole batch. Tags may be created in
  the "Person hinzufügen" form the same way.
- **Tag management** (rename, delete) sits behind "Tag bearbeiten" in the list of
  the tag itself; deleting asks for confirmation and returns to "Alle".
- **Cards stay at 0** in WP1 (they are buttons without a filter yet); WP2 fills
  them and gives the circle in a row its meaning.

Small decisions taken while building WP2, where the plan was silent:

- **Boundaries.** `erkaltet` is strictly more than `min(2 × interval, 180)` days
  (exactly at the limit is still `ueberfaellig`); `bald` includes "due today"
  (`faellig_am == heute`), `ueberfaellig` starts the day after. A person with
  no Kontakt stays `unbekannt` even if a next date is set: the override waits
  for the first Kontakt. A next date in the past with a recent contact makes the
  person `ueberfaellig`; `erkaltet` is judged on the last contact only, so an
  override never hides a cold bond.
- **Rough contact meets the defaults.** "Vor ein paar Monaten" was 120 days in
  the first cut; the cold limit at the default interval of 56 days is 112, so
  such a batch was `erkaltet` at once. Changed in WP3 on review to **90 days**:
  a quick-add batch with "a few months ago" now starts as `ueberfaellig`
  (90 > 56 and 90 ≤ 112), a bond to call soon, not a bond already lost.
  "Diesen Monat" (15) is `ok`, "Über ein Jahr her" (400) is `erkaltet`. The
  approximate dates already stored in a database stay as they were (no
  migration; a rough contact is only a starting point and the next real Kontakt
  replaces it).
- **Row badge ("Plakette").** `unbekannt` → "noch kein Touchpoint"; `erkaltet` →
  "erkaltet"; `ueberfaellig` → "überfällig seit N Tagen"; `bald` → "fällig heute
  / morgen / in N Tagen" (more useful than "vor 6 Wochen" for someone about to be
  due); `ok` → relative time of the last contact. Relative time: 0 days
  "heute", 1 "gestern", 2–13 "vor N Tagen", 14–59 "vor N Wochen" (`N = days ÷
  7`), 60–364 "vor N Monaten" (`N = days ÷ 30`), from 365 "vor über einem Jahr".
  The row circle takes the colour of the state (palette variables of the card it
  belongs to); the word always stands next to it.
- **Row text.** The first line of the latest note of a *real* Kontakt; the
  profile note only while the person has no real Kontakt. A `schaetzung` has no
  note and does not count as a conversation, so a person with only a rough
  contact still shows the profile note. A real Kontakt without a note shows no
  second line.
- **Touchpoint eintragen.** Any day up to and including today in the user's time
  zone is accepted (back-dating is normal after a busy week); a later day is
  rejected with a message. The art starts on "Anruf". Logging always clears the
  next date, even for a back-dated entry. Editing or deleting a Kontakt never
  touches the next date (it is not restored). A `schaetzung` can only change its
  date. A deleted last Kontakt returns the person to `unbekannt`.
- **The sheet** is a `role="dialog"` over the Personenseite (centred on the Mac,
  bottom sheet on the phone), not a native `<dialog>`: HTMX swaps it in, and
  closing (Abbrechen, Escape, a click beside it) needs no server because nothing
  is saved while it is open. The circle in a row selects the person and opens the
  sheet in one request (`GET /personen/<id>/kontakt/neu`).
- **Cards are links** (`?karte=aufmerksamkeit|erkaltet|woche`) so the state lives
  in the URL. A card click is list navigation like the sidebar: it closes the open
  person, keeps tag and search, drops `filter` (Noch kein Touchpoint / Archiv hold
  nobody that a card could count). Clicking a sidebar entry resets the card. In
  the Archiv `karte` is ignored. The counts are always over all active people,
  whatever tag, search or card is open; opening a person or saving keeps the card
  in the URL. Empty card lists have their own sentence.
- **Sort order** with a card open follows §6 (erkaltet first, then `faellig_am`,
  then name); every other list stays by name. Cards, rows and the Personenseite
  all read the same `faelligkeit.bindungen()` result for the request: one query
  for all of a user's people, state and sorting in Python (a few hundred people).
- **Personenseite** (order changed after 0.1.0, see below) has several forms of
  one kind around "Zuletzt besprochen", because HTML has no nested forms. Both save on `change` as
  before. "Fällig am", the state and the last contact sit under Intervall and
  Nächster Termin and are redrawn (`hx-swap-oob`) after every change that touches
  them. Archived people show "Im Archiv: keine Erinnerung." instead.
- **Zuletzt besprochen** edits inline: "Bearbeiten" swaps one entry for a form,
  save redraws the whole history plus Fällig am, rows, cards and sidebar (a date
  change can reorder it and change the state); "Löschen" asks first
  (`hx-confirm`).
- **Search keeps the open person.** The person is not in the search form (it
  changes without the form being redrawn), so the search request reads it from
  `HX-Current-URL`; a person that is not the user's is dropped silently.
- **Card labels on narrow screens** shrink with a container query on the card
  row instead of hyphenating; the label text stays.
- **Code layout.** The helpers every router needs (view in the URL, context for
  sidebar/cards/list, building parts, answers) moved from `routen/personen.py`
  to `bindung/web/ansicht.py` so `routen/kontakte.py` does not import another
  router's private names. No behaviour change.
- **Hook for WP3.** `ansicht.stichtag_personen()` returns the people with a
  Stichtag in its lead window (empty until WP3); `faelligkeit.karten_nummern()`
  already adds them to "Diese Woche" without changing anyone's state.

Small decisions taken while building WP3, where the plan was silent (and one change
the review asked for, recorded with WP2 above: "a few months ago" is now 90 days):

- **Dates.** A Stichtag or a family birthday is entered in three fields (day,
  month as a name, optional year) and stored as `YYYY-MM-DD` or `--MM-DD`. The
  year must be 1900 or later and not in the future; 29 February is valid without
  a year. Shown as "24. März" or "24. März 1986".
- **Next occurrence.** The next day on or after today on which the day and month
  come round; a leap day falls on 28 February in a common year. The age is the
  year of that next occurrence minus the birth year, shown as "wird 40" for a
  birthday and "10 Jahre" for the others; nothing is shown without a year, or
  when the difference is below 1.
- **Lead window.** A Stichtag is in its window when its next occurrence is today
  or at most `vorlauf_tage` days away (the date's own value, else the user default
  of 7). `vorlauf_tage = 0` means "only on the day". The value is 0 to 365. An
  empty label falls back to the word of the kind ("Geburtstag", "Jahrestag");
  `sonstiges` needs a name.
- **Badge.** A row shows one Stichtag badge: the nearest one in its window. Text
  is kind plus time ("Geburtstag in 4 Tagen", "Jahrestag heute"); a family
  member's birthday carries the name ("Geburtstag Mia in 3 Tagen") so the parent
  can tell whose day it is, and a `sonstiges` Stichtag uses its own label. The
  badge sits under the state badge, in a small frame in the `--woche` colour; the
  state badge is unchanged. Archived people have neither badge nor card entry,
  but their Stichtage stay listed on their page.
- **Family birthdays** use the default lead time and are edited only through the
  family entry (a direct change or delete of that Stichtag is refused with a
  message). A linked person's own birthday is a separate Stichtag of that person;
  the counterpart entry never receives the birthday, so nothing is duplicated and
  the family-entry birthday stays the parent's Stichtag. A person with both shows
  up for both days; that is fine for v1.
- **Name of an entry** is its own field: empty when linking, it takes the other
  person's name at that moment; later renames of the person do not change it. The
  page always shows the linked person's live name as the link ("In der App: ...",
  or the name itself as the link when both are equal).
- **Linking rules.** A person cannot be linked to themselves; an entry that is
  already linked (to anybody) is refused until "Verknüpfung lösen"; two entries
  of one person may point to the same other person (a sibling who is also a
  business partner gets two counterparts). The counterpart's free text is copied
  for `sonstiges`; for the other roles the free text is dropped, also when the
  role is changed later. The inverse role and the name of a counterpart are
  edited on its own side and never touch the original.
- **Unlinking and deleting** follow §5 literally: the entry where the user acts
  stays as a plain entry (on unlink) or goes (on delete), the other side is removed
  together with its birthday Stichtag. This holds from either side (the counterpart
  is not "second class"), so the confirmation names what disappears on the other
  page.
- **Picker "In der App".** A search field plus up to eight results as radio
  options, over the user's active people (name, company, city, tag; the same
  search as the list); no text, no results. Enter in the field does not submit the
  form. The model also accepts an archived person as the link target; the page
  never offers one.
- **Page behaviour.** "Hinzufügen" is a `<details>` form that is closed until
  needed or until it holds a rejected input. Every change redraws both sections
  (the birthday of a family member is a Stichtag) plus row, cards and sidebar
  through `ansicht.familie_teile`. A rejected input in an entry's own form answers
  422 and redraws that form with the message; any other rejection redraws the
  section with the message on top. A person or entry of another user is a 404, also
  as link target.
- **One query for the lead window.** `kontext_bauen` reads `stichtage.im_vorlauf`
  once and derives both the card set and the row badges from it;
  `ansicht.stichtag_personen` keeps its signature as the single-purpose view of the
  same list.

Small decisions taken while building WP4, where the plan was silent:

- **Calendar file.** Hand-written RFC 5545 in `bindung/kalender.py`: CRLF, lines
  folded at 75 octets without splitting a UTF-8 character, text escaped
  (`\\ \; \, \n`), `X-WR-CALNAME:Bindung`, `REFRESH-INTERVAL` and
  `X-PUBLISHED-TTL` of one hour, `TRANSP:TRANSPARENT` so all-day events do not
  block the day. `DTSTAMP` and `LAST-MODIFIED` are the time of the request (UTC).
  UIDs are `stichtag-<id>@bindung` and `melden-<person_id>@bindung`.
- **Stichtag events.** One yearly all-day event per Stichtag of a non-archived
  person; `DTSTART` is the stored year if there is one, else the next occurrence.
  Titles: "Geburtstag Anna Beispiel" for a birthday with the default label, a
  family member's birthday "Geburtstag Mia Beispiel (Anna Beispiel)", everything
  else "Anna Beispiel: <label>". **No age in the file** (§9 had "wird 40"): the
  description belongs to the whole series, and a calendar also shows next year's
  and the past years' instance, where a fixed age would be wrong. With a known
  year the description states the fact instead ("Geburtsjahr 1986", "Seit 2012");
  the age stays in the app (badge, Personenseite). Revisit with a per-instance
  override (`RECURRENCE-ID`) if the user misses it.
- **29 February.** `BYMONTHDAY=-1;BYMONTH=2` is not understood everywhere, so a
  year-less 29 February starts on the next real 29 February (never on 28
  February, or the series would never fall on the 29th) with a plain
  `FREQ=YEARLY`; what the calendar does in common years (skip, 28th or 1st March)
  is its own affair. The app itself still shows it on 28 February (WP3).
- **"Melden bei" events.** For every non-archived person whose state is not
  `unbekannt`: one all-day event on `faellig_am`; when that day is past (overdue
  and cold people) on the **next Sunday, today included** (`DURCHSICHT_WOCHENTAG`),
  the day of the weekly review, so the reminder rings once a week instead of
  every morning (changed on the user's request after WP4; the first cut moved
  them to today each day). The event moves with the same UID when a Kontakt is
  logged. All events are `TRANSP:TRANSPARENT`, so they show as free, not busy. Description "Zuletzt besprochen: <first line of the latest real note>"
  (a Schätzung has no note, so none). The alarm is `TRIGGER:PT9H`, a duration
  after the start of the all-day event, i.e. 09:00 in the zone the calendar is in:
  portable, and no UTC computation from the user's time zone is needed. Not
  verified in Apple Calendar itself (no device here); the value is the one Apple
  writes for "on the day, 9 AM". Stichtage get no alarm: the app's own lead time
  is the reminder there.
- **Routes and the open door.** `/kalender/<token>.ics` answers without login;
  an unknown token is the same bare 404 as any unknown page, whatever it looks
  like (no near-miss hint; the lookup is one equality in SQLite). The open door is
  now only `/kalender/*.ics` (`basis.ist_offen`), not the whole `/kalender/` prefix,
  so `/kalender/herunterladen` is behind the login by the same door as every other
  page. Both answer `text/calendar; charset=utf-8` with `Cache-Control: private,
  no-store`; the download adds `Content-Disposition: attachment;
  filename="bindung.ics"`.
- **Rotating the address** writes a new `secrets.token_urlsafe(32)`; the old URL is
  a 404 at once. A confirmation (`hx-confirm`) names the consequence.
- **Address on the page.** `basis.aussenadresse(request)` gives scheme and host:
  `https` when `BINDUNG_SICHER=1`, otherwise `X-Forwarded-Proto` if it is `http` or
  `https`, otherwise the request's scheme; host from `X-Forwarded-Host` or `Host`
  (checked against a host pattern, else the request's). A helper instead of
  middleware: the values only end up in the user's own page, so the proxy does not
  have to be trusted and no global request state is needed. Both `webcal://` and
  `https://`/`http://` addresses are shown, each with a copy button
  (`navigator.clipboard`, falling back to `execCommand`).
- **Settings page** is its own page (one column, back link to `/`), not a pane.
  Each section has its own form with a save button and "Gespeichert" (unlike the
  Personenseite there is no save-on-change: a half-typed password or a time zone
  scrolled past in the list must not be sent). HTMX swaps only the section; a
  rejected value is a 422 with the section redrawn with what was typed (passwords
  never); without script the same routes answer the whole page.
- **Passwort ändern.** `auth.passwort_aendern` checks the current password and
  keeps the session it was called from (`passwort_setzen(..., behalte_token=)`
  deletes all other sessions of the user, including a stolen cookie). A wrong
  current password counts as a failed attempt for the failed-login delay (same
  per-name counter as the login), and the delay refuses even the right password
  until it has run out; the answer is a 422 with the text, not 429, because the
  page only swaps 2xx and 422.
- **Erinnern.** Interval 1 to 3650 days, lead time 0 to 365, time of day `HH:MM`
  (a time field's `HH:MM:00` is accepted), saved all or nothing. Time zones: a
  list of 40 common IANA zones, Europe/Berlin first, each checked by `zoneinfo`; a
  zone already stored outside the list stays selectable (and only that one), so
  a value set by hand in the database is not lost. Changing the zone or the
  defaults needs no migration: states are computed when read. The time of the
  Tagesmeldung is stored now, the note under the field says the push itself comes
  later (WP5; update that text then).
- **Diktat.** `de-DE` ("Deutsch") or `en-US` ("Englisch (USA)") in
  `nutzer.diktat_sprache`; WP6 reads it.
- **Code layout.** `bindung/kalender.py` (file, address, token), `bindung/
  einstellungen.py` (read, validate, save), routers `routen/kalender.py` and
  `routen/einstellungen.py`, templates `einstellungen.html` and one partial per
  section (`_einstellung_<abschnitt>.html`). Two conventions went into
  `docs/design_conventions.yaml`.

Small decisions taken while building WP5, where the plan was silent:

- **Digest content.** Waiting = state `ueberfaellig` or `erkaltet`, plus `bald` with
  `faellig_am == heute`; plus every Stichtag in its lead window (today counts). Text, one
  line per fact: "3 Personen warten · 1 Geburtstag" (Stichtage counted per kind:
  Geburtstag, Jahrestag, Stichtag for `sonstiges`), then up to three names, cold first,
  then by due date, then name, with " …" if more, then the nearest Stichtag with the
  words of the calendar title ("Geburtstag Mia Beispiel (Anna Beispiel) in 3 Tagen" for
  a family birthday). Title "Bindung". The click opens `/?karte=aufmerksamkeit`, or
  `/?karte=woche` when nobody waits and only Stichtage are in their window.
- **Hinweis, not banner.** The strip is `#hinweis` above `.app` (not inside the list):
  on the phone the app opens on the sidebar, and a strip in the list would be seen only
  after the first tap and lost on every list change. It shows the same count and names
  (two lines at most), "Benachrichtigungen erlauben" and "Heute ausblenden". With a
  subscription anywhere the server renders it `hidden`; `bindung.js` shows it when *this*
  browser has none and removes it when it has one. So a second device without push still
  gets the strip and the ask. The Safari/Dock sentence appears in the strip only when the
  browser cannot do push at all (no `PushManager`), and always in the settings.
- **Permission** is asked only by a click on `data-push-aktivieren`; a denied browser gets
  the strip without the button. A subscription is re-posted once a day (localStorage) so a
  replaced database or a switched user heals itself.
- **Subscriptions.** `push_abo.endpunkt` is unique across users, so a browser that signs
  in as another user *moves* to that user (one Mac, two people) instead of failing. The
  server only accepts `https` endpoints with a host name (no IP literal, `localhost`,
  `.local`, `.internal`) and base64url keys, because it will POST to that address. Not
  checked: a public name that resolves to a private address (an authenticated user could
  make the server send an encrypted POST there); revisit before the server faces the
  internet with several users. `DELETE /push/abo` answers 204 even for an unknown
  endpoint and only ever touches the caller's rows.
- **Keys.** `vapid.json` holds `privat_pem`, `oeffentlich` (URL-safe base64, uncompressed
  point, what `subscribe()` wants) and `sub`; written to a temp file with mode 0600 and
  hard-linked to the final name, so two first starts cannot overwrite each other. The `sub`
  is `mailto:bindung@localhost` unless `BINDUNG_PUSH_KONTAKT` is set (read at send time).
  Some push services may insist on a real address (Apple is the one to watch); not
  verified without a device. Messages carry a TTL of 12 hours: a morning digest is
  worthless the next day. No icon is sent yet (no manifest before WP7; `sw.js` uses
  `icon` as soon as the server sends one).
- **Daily task.** `tagesaufgabe.tick(con, jetzt)`; the loop wakes every 60 s, starts with
  the server (FastAPI lifespan) and runs the tick in a worker thread (sending waits for
  the network). The user's time has passed when local `HH:MM >= tagesmeldung_zeit`; the day
  is the user's local date. **The `digest_protokoll` row is the lock:** claiming the day
  is one conditional upsert (`... WHERE letzter_versand_am IS NOT excluded...`), and only
  the process whose statement changes a row sends. This holds for two processes on one
  data folder (reload, a second instance) without a lock file. The claim comes *before*
  sending: a crash in between loses a digest rather than doubling it. A user without
  subscriptions, or with nothing due, still gets the day recorded; a person who becomes
  due later that day waits for tomorrow. A server that starts at 17:00 with the time
  08:00 still sends today's digest once; yesterday's is never sent late (in a zone far
  behind the server the *local* previous day can be sent once at start, that is today's
  rule applied to that zone). Every user is wrapped in try/except, the loop catches
  everything. `BINDUNG_TAGESAUFGABE=0` turns the loop off; the tests do.
- **Settings.** "Benachrichtigungen" is its own section under "Erinnern", not a block in
  its form: saving Erinnern swaps its whole section and would erase the status the
  script just wrote. The status (`erlaubt und angemeldet`, `noch nicht erlaubt`, `nicht
  erlaubt`, `nicht unterstützt`) is computed by the browser; the count of registered
  browsers and the result of "Testmeldung senden" come from the server, and the section
  reloads itself (`GET /einstellungen/benachrichtigungen`, HTMX only) after every
  subscribe and unsubscribe. The test message replaces the section with its result ("an
  2 Browser gesendet", "Nur 1 von 2 ..."); a dead browser is dropped on the way.
- **`/sw.js`** is open (no login, no data in it), served with `Cache-Control: no-cache`
  and `Service-Worker-Allowed: /`; the worker only handles `push` and `notificationclick`
  (focus a window and navigate it to the URL, else open one), no `fetch`, no cache.
- **Session renewal** (WP0 review note): the expiry is rewritten only when it is more than
  one day below the full 30 days, so at most one write per session per day. The cookie is
  still re-sent every time; the database governs.
- **Not verified here:** real delivery in Safari, Chrome and Firefox (the browser pane
  denies the permission, so the flow was driven with a stubbed `Notification` and
  `PushManager.subscribe`, a real `/sw.js` registration and a stubbed `webpush`), and
  whether Apple's push service accepts the default `sub`.

Small decisions taken while building WP6, where the plan was silent:

- **No language toggle on the button.** Section 8 put one on the button; the setting
  exists since WP4 (Einstellungen › Diktat, two taps from the sidebar), so the button stays
  a single round button. The language reaches the script as `data-diktat-sprache` on
  `<body>`, rendered from `nutzer.diktat_sprache` (`de-DE` on the login page), so a change
  applies from the next page load, not to a page that is already open.
- **The frame is in the templates, the button comes from the script.** Every
  `<textarea data-diktat>` sits alone in `<div class="diktat">` (checked by
  `tests/test_web_diktat.py`); `bindung.js` adds the button, only if `Diktat.verfuegbar()`,
  on load and on `htmx:afterSettle`, by event delegation for the clicks. Wrapping the field
  from script would move it in the DOM and take its focus (the Kontakt sheet has
  `autofocus`), and would flash unstyled on every swap.
- **The button sits in a strip below the field, not inside its corner.** The field keeps
  its full height; the 44 px button is right-aligned under it and what the browser is
  recognising (grey, italic, two lines at most) stands to its left. A button floating inside
  the corner covers text as soon as the field scrolls and sits on the scrollbar on desktop;
  verified at 1024 px and 375 px. Errors come as a red line under the strip (`role="alert"`).
- **`diktat.js` writes final text itself, the UI listens.** `Diktat.starten(feld, sprache)`
  inserts every final result at the cursor (else at the end, with a space to the
  neighbours, `setRangeText`), fires `input`, and at the end of the session `change`: the
  Personenseite saves on `change` (section 7), and a programmatic insert does not fire it by
  itself. The field is never written with interim text. Events on the field: `diktat:start`,
  `diktat:zwischen`, `diktat:fehler`, `diktat:ende`. The backend is one object chosen at load
  (`backend`, shape in the file's header); a server-side transcriber replaces it. The second
  backend is not written.
- **Where the text goes.** The button keeps the field focused (`mousedown` is cancelled) so
  the cursor stays and on the phone the keyboard stays as it was; a keyboard click (detail 0)
  moves the focus back to the field first. The cursor is read at every insert while the field
  has the focus, otherwise the end position after the last insert is used.
- **One recording, and what ends it.** Starting another field stops the first (`stop()`, so
  its last words still arrive). The same button again, Escape (capture phase, so a Blatt
  behind does not close at the same time; the second Escape closes it), closing the Blatt
  ("Abbrechen", click beside it) and the field leaving the page all end it. The browser
  also ends a session by itself after some silence; the button then goes back to "Diktieren"
  and the user taps again. There is no automatic restart.
- **Errors are German and end the session**: `not-allowed` and `service-not-allowed` (with
  the hint to allow the microphone in the browser's settings), `no-speech`, `network`,
  `audio-capture`, `language-not-supported`, anything else with its code. `aborted` is silent.
- **The audio leaves the server's reach.** The recognition of Safari and Chrome sends the
  audio to Apple's or Google's service; Bindung's server never sees it. This is the
  price of "no model to install" (above) and the one exception to "nothing leaves except
  push" in section 2, now also named in `CLAUDE.md` and in the release notes. Who does not
  want it dictates with a Mac dictation app (works in every field) or waits for the
  server-side backend.
- **Not verified here:** real speech recognition. The browser pane's Chromium has
  `webkitSpeechRecognition`, but the pane has no microphone path; the whole flow (button,
  recording state, interim line, final insert at the cursor, `input` and the save `POST`
  on the Personenseite, switching fields, Escape, the four error codes) was driven with a
  fake recognition class defined on `window` before `diktat.js` was re-evaluated against it.
  Safari on iPhone (a second `webkitSpeechRecognition` on the same page, microphone
  permission in an installed web app) is untested.

Found in the review of WP6:

- **Static files carry a content fingerprint.** `basis.statisch('bindung.js')` renders
  `/statisch/bindung.js?v=<10 hex of sha256>`; `basis.html` uses it for the stylesheet
  and all scripts. Without it the browser kept the pre-WP6 `bindung.js` and `stil.css`
  from its cache after the update and showed no mic button, although the code was
  right. Computed once per process (`functools.cache`); `serve --reload` restarts the
  process. `/sw.js` keeps its own `no-cache` header, as a service worker must.

Decided while building WP7 (Mac app, PWA, first release):

- **The symbol is two overlapping rings** (`statisch/symbol.svg`), accent colour on
  transparent, no text: it reads at 16 px in a tab and at 512 px on the Home Screen.
  The SVG carries both accents (light and dark) in a `prefers-color-scheme` block, so the tab
  icon follows the theme. The PNGs (`symbol-180`, `-192`, `-512`, `-maskable-512`,
  `-menue`) are written by `werkzeuge/symbole/erzeugen.py`, which draws the rings and the
  rounded square itself with the standard library (about 100 lines, no dependency).
  Reason: `cairosvg` needs the native cairo library (not on this Mac), `rsvg-convert` is not
  installed, and `qlmanage -t` returns an opaque white background and renders in the
  colours of the current light or dark system appearance. The app icons are an accent
  square with white rings: `symbol-180` and `-maskable-512` full bleed (iOS and Android
  round or crop them), `-192` and `-512` and the `.icns` with rounded corners and
  transparent edges. The `.icns` is built on demand by `bauen.sh` (`iconutil`) and not
  committed; the PNGs are committed, and `tests/test_web_manifest.py` compares them byte
  for byte with what the script produces now.
- **Manifest** at `/manifest.webmanifest`, built in Python from `basis.palette()` (which
  reads the `:root` blocks of `stil.css`), because templates carry no colour values. `theme_color`
  and `background_color` are the light `--grund`; the `<meta name="theme-color">` pair covers
  light and dark with `media`. Open route (the browser fetches it without cookies), as are
  `/healthz` and `/statisch/`. The link in the head carries a `?v=` fingerprint of the
  manifest content, like the static files. No `fetch` listener in `sw.js`: still no offline
  mode in v1; the service worker stays push-only. The push payload now carries
  `icon: /statisch/symbol-192.png`, which the service worker already passed on.
- **The Mac app starts on port 8788** and does not touch 8785, so `bindung serve` and the
  app can exist side by side. If Bindung answers on 8788 the second double click only opens
  the browser. `/healthz` returns `{"app": "Bindung", "version", "daten"}`, where `daten` is a
  12-character hash of the data folder path (not the path: the route is open).
- **One daily task per data folder.** The app process is the one that is always on, so the
  daily task runs there. If a `bindung serve` already answers on `BINDUNG_PORT` (default 8785)
  with the same `daten` hash, the starter switches its own task off and says so. This is a
  courtesy, not machinery: two tasks could not send twice anyway, because the day is claimed
  by one atomic statement on `digest_protokoll` (`tagesaufgabe._beanspruchen`, only the
  caller whose `UPDATE` changes the row sends). A `bindung serve` started *after* the app is
  not detected; the claim still keeps the digest to one per day.
- **"Beenden" only in the Mac app.** The starter sets `basis.BEENDEN`; only then does the
  sidebar show the button (`data-beenden`, handled in `bindung.js`) and `POST /api/beenden`
  work. Everywhere else it is 404. It needs the login like every route and refuses a foreign
  `Origin`. The menu bar has "Bindung öffnen", "Datenordner zeigen" and "Beenden"; its image
  is `symbol-menue.png` (the rings, black on transparent, set as a template image so macOS
  tints it for light and dark bars). No Dock icon (`LSUIElement`).
- **The first user is created in the app.** Someone who double-clicks the DMG has no terminal
  for `bindung nutzer anlegen`, and section 4 says there is no self-signup. So *only* when the
  process runs as the Mac app (`BEENDEN` set) *and* there is no user yet, `/anmeldung` leads to
  `/einrichten` (name, password twice, minimum 8 as everywhere) and logs that user in. With
  one user the route is 404 for good. A server (`bindung serve`, a container) never offers
  it: a freshly started empty server must not be claimable by whoever reaches it first. More
  users come from the CLI as before.
- **Packaging** is health's pattern: `werkzeuge/paket/bauen.sh` (icons, PyInstaller with
  `bindung.spec`, smoke test, `dist/Bindung-<version>-mac.dmg`), unsigned (a DMG built here
  opens without a warning; a downloaded one needs right-click → Öffnen the first time). The
  smoke test starts the built app in an empty data folder on port 8798 and goes through the
  first start (setup page, login), the pages, manifest and icons, `/sw.js`, the fingerprinted
  stylesheet, and `POST /api/beenden`. `zoneinfo` reads the system's time zone database
  (every Mac has it); the `tzdata` package would be bundled if present.
- **Release 0.1.0 is tagged locally and published by hand** (`docs/release.md`); the notes
  come from `CHANGELOG.md` through `werkzeuge/release_notes.py`.

Decisions after the first feedback on 0.1.0:

- **The word in the interface is "Touchpoint", the word in the code stays
  `kontakt`.** "Kontakt eintragen" sounded like adding a phone-book entry. The
  interface, the help texts, the changelog from the next release on and CONTEXT.md say
  Touchpoint (der Touchpoint, die Touchpoints, "einen Touchpoint eintragen"; the
  list of past ones is still "Zuletzt besprochen", the kinds are unchanged). The
  table `kontakt`, the modules, routes, template names and CSS classes keep the old
  word: renaming them needs a migration and touches thousands of lines with no gain
  for the user. This is the one deliberate split between UI word and code word and is
  recorded in CONTEXT.md ("Touchpoint ... im Code `kontakt`"). The published 0.1.0
  notes keep their wording (history). Where this plan says "Kontakt" for the domain
  object in §5 and §6, it means the Touchpoint. "Den Kontakt halten" as an idiom
  ("keep in touch", login page, manifest, README) stays.
- **Personenseite order follows §7 again.** Header (name, company, role), tags, the
  contact links, phone, email, city, how we met, **Profilnotiz**; then the button
  "Touchpoint eintragen", "Zuletzt besprochen", "Angehörige", "Stichtage"; then
  Intervall, Nächster Termin, state and Fällig am; Archivieren. The WP2 layout had
  pushed the profile note under the history, where the user could not find it. The
  tag chips are forms themselves, so "one form above the button" is not possible;
  there are three forms of the same kind (header; phone to profile note; Intervall
  and Nächster Termin), all `POST /personen/<id>`, each with its own fields and
  saving on `change`. A hint under the Profilnotiz says when it is saved.
- **Appearance is stored per user, not per device.** `nutzer.darstellung`
  (`system` | `hell` | `dunkel`, default `system`; migration 2, existing users get
  `system`). The server writes it as `data-darstellung` on `<html>` in the first byte
  of the page (no flash; a browser-side store would flash and would not follow the
  user to another device), together with `color-scheme` and the two `theme-color`
  lines. `stil.css` has the two device blocks unchanged and repeats their values under
  `:root[data-darstellung="hell"|"dunkel"]`; no new colours (`tests/test_design.py`
  keeps the four blocks equal). Login and setup have no user and follow the device.
  Saving the section sends `HX-Trigger: {"darstellung": ...}` and `bindung.js` updates
  the live page. The favicon `symbol.svg` still follows the device (its own media query).
- **"Verknüpfen" opens with the name.** The search field of an Angehöriger without
  link is prefilled with its name and the matching people are rendered on the server
  (`person_daten` -> `vorschlaege`), so the user picks without typing; the field stays
  editable and uses the same `kandidaten` route as before. The create form stays as it
  is (the name is typed first).

Decisions while building the MCP server (section 14):

- **Who the bot is is decided once, at the start, and again on every call.**
  `bindung mcp --nutzer NAME` checks the name against the data folder and exits with a
  message on stderr if it is unknown, or if there is no user, or if there are several
  and no name was given (a client that shows a dead server is easier to fix than one
  that answers every call with an error). Each tool call opens its own connection and
  resolves the user again (`werkzeuge._kontext`), so nothing is cached across calls and
  a number that belongs to another user is simply "not there" (`NichtGefunden`
  becomes "Es gibt keine Person mit der Nummer ..."), indistinguishable from one that
  never existed.
- **A name is accepted only if it hits exactly one person.** The whole name wins over a
  part of a name ("Ben" with a person called "Ben" and one called "Ben Muster" is the
  first); several hits, including two people with the same name, are refused with the
  candidates and their numbers. By name only active people are found; by number an
  archived one is too, because the pages show it as well. The answer always repeats the
  full name and number so the bot can notice a wrong pick.
- **The bot cannot do a thing twice by accident.** An identical Touchpoint (person, day,
  kind, note) or Stichtag (kind, date, name) is refused with the number of the existing
  one; a person with an existing name needs `trotzdem=true`. A client that repeats a call
  after a timeout therefore does no harm. No tool undoes or deletes anything; the answer
  says what to fix in the app.
- **Tags by name are created if missing, and the answer says so.** The brief asked for
  "tags by name"; refusing unknown tags would make the first sitting miserable, and a typo
  is visible in the answer ("Neu angelegte Tags: ...", with a pointer to `tags`).
  Matching ignores case like the app. Everything that can fail (empty tag, unknown rough
  contact) is checked before the person is created, so a refused call leaves nothing.
- **The rough last contact reuses the Schätzung.** `kontakte.schaetzung_eintragen` is
  the single-person form of what "Mehrere hinzufügen" does; no new kind.
- **`profilnotiz_setzen` replaces, but shows what stood there**; `anhaengen=true` adds a
  line instead. Replacing is what the page does when the field is saved; the echo makes it
  recoverable from the conversation.
- **`heute` and `gestern` are accepted as a date** in `touchpoint_eintragen`, nothing else
  beyond the page's ISO day. A model often means exactly that, and it does not know the
  user's time zone's "today"; every `person` answer also says "Heute ist ...".
  `E-Mail` as a kind is read as `email`; other kinds, dates and Stichtag fields get the
  page's own error text.
- **Arguments are checked against the announced schema** (types, required, no unknown
  parameters; `additionalProperties: false`), so a model that invents a parameter is told
  instead of silently ignored. Read tools carry `readOnlyHint`, all tool descriptions say
  whether they write ("SCHREIBT").
- **The glossary is `CONTEXT.md` next to the package.** No second copy of the vocabulary
  to keep in step; the Mac app bundles the file.
- **The Mac app starts the bot access too** (reviewed 2026-11-12): whoever installs from
  the .dmg has no `bindung` in the terminal, so `werkzeuge/paket/start.py` hands
  `Bindung mcp --nutzer NAME` to the CLI, the bundle carries `CONTEXT.md`, and the smoke
  test drives handshake, tools, one write and the glossary in the built app. A client is
  configured with `/Applications/Bindung.app/Contents/MacOS/Bindung` as the command.
- **0.1.1 was never published; the release is 0.2.0** with the 0.1.1 feedback, the bot
  access and the empty-search button together, because the user wanted the release to
  include MCP.
- **The model reads the notes.** Touchpoint notes and Profilnotiz are in the answers,
  because "what did Anna and I talk about?" cannot be answered without them. The data stays
  on the machine, but the client's model sees what a tool returns; `docs/mcp.md` says so.
- **Empty search offers to create the person.** Under "Niemand gefunden für ..." the
  list shows a primary button `„<Suchtext>“ als Person anlegen` (the trimmed search
  text, escaped). It loads `GET /personen/neu?name=<text>` into the person pane, the
  same form as "Person hinzufügen", with the name field filled (at most 200
  characters, the field's own limit). The open sidebar tag is still preselected; the
  search text stays in the field and in the URL, because the request only changes the
  pane. After "Anlegen" the new person is selected exactly as after "Person
  hinzufügen": the list stays filtered by the search, and if the saved name does not
  match it the person is still open on the right but absent from the list (and the
  empty sentence with the button is still there). We chose not to clear the search:
  the user sees the same list they were in, and clearing would also lose a tag or card
  context. **Not offered in the Archiv**, because a new person is active and would
  vanish from the list that is open; the same sentence there stays text only.

## 14. MCP server (planned and built 2026-11-12)

The user wants to use Bindung through a bot: ask questions ("wen habe ich lange
nicht gesprochen?", "was haben Anna und ich zuletzt besprochen?"), log a
Touchpoint after a call, and create a person on the fly. The way in is the
Model Context Protocol, like `finctl mcp` in the user's finance app: JSON-RPC
over stdin/stdout, no port, no library, one message per line
(`bindung/mcp/protokoll.py` for the handshake, `tools/list`, `tools/call`,
`resources/list`, `resources/read`; `bindung/mcp/werkzeuge.py` for the tools).
Copy finctl's structure; the difference is that here the bot **writes for
real**, because the user asked for it.

- **Who the bot is.** `bindung mcp --nutzer <name>` acts as exactly that user on
  the local data folder; every tool goes through the same functions as the
  pages (`personen.py`, `kontakte.py`, `faelligkeit.py`, `stichtage.py`,
  `angehoerige.py`), never through SQL, so `nutzer_id` filtering and the state
  rules hold. Without `--nutzer` and with exactly one user, that user. Over the
  network (the later Docker deployment) the same tools sit behind an HTTP
  transport with a per-user token from Einstellungen; that is a second step,
  not v1 of the MCP.
- **Tools, read:** `personen_suchen` (text over name, firma, ort, tag; returns
  id, name, firma, tags, Zustand, letzter Touchpoint), `person` (everything the
  Personenseite shows: fields, Zuletzt besprochen, Angehörige, Stichtage, Fällig
  am), `wer_wartet` (the three cards with names, sorted like the app),
  `diese_woche` (due people and Stichtage in their window), `tags`.
- **Tools, write:** `person_anlegen` (name, optional firma, rolle, telefon,
  email, ort, herkunft, profilnotiz, tags by name, optional rough last
  contact as in "Mehrere hinzufügen"), `touchpoint_eintragen` (person id or
  unambiguous name, art, datum default today, notiz; same rules as the sheet:
  no future date, clears the next date), `profilnotiz_setzen`,
  `stichtag_anlegen`. No archiving, no deleting, no tag management, no settings
  through the bot in v1: a wrong write there is hard to notice.
- **Resources:** `bindung://glossar` (CONTEXT.md, so the bot uses the app's
  words) and `bindung://heute` (the digest text for today).
- **Answers are text**, formatted as the app formats them (relative times,
  states, badges), with ids in brackets so a follow-up call can refer to them;
  errors are `isError` answers with the German message the page would show.
- **Safety:** stdout belongs to the protocol (everything else to stderr, as
  finctl does); the tool descriptions say what each one changes; a name that
  matches several people is refused with the candidates instead of guessed.
- **Done means:** `bindung mcp` registered in Claude Desktop or any MCP client
  can answer "wer wartet?", log "Anruf mit Anna, wir haben über X gesprochen"
  and create a person with tags, each visible in the app at once; tests drive
  the protocol over pipes with recorded JSON-RPC lines, plus unit tests per
  tool including user isolation; a page in `docs/` shows the client
  configuration; CHANGELOG entry for users.
