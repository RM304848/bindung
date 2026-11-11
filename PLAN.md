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
`bindung/starter.py`: server on `127.0.0.1:8788`, menu-bar icon, no Dock icon,
opens the browser. Matters more here than in finctl: push digests and the
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
  erzeugen"), push on/off, dictation language.

## 5. Domain model

Vocabulary is in CONTEXT.md. Tables (all with `nutzer_id` where user data):

| Table | Holds |
|---|---|
| `nutzer` | name, password hash, digest time (default 08:00), time zone, default interval days (56), default lead days (7), calendar token, dictation language |
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
    with a grey "noch kein Kontakt" label in the list and in a sidebar filter.
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

- **Left sidebar:** Alle, Noch kein Kontakt, Archiv; then one entry per tag
  with its count; "Tag hinzufügen" at the bottom; user name and Einstellungen
  at the very bottom.
- **Middle column:** the three cards with counts; a search field (name,
  company, city, tag; filters as you type); "Person hinzufügen" and
  "Mehrere hinzufügen"; the list. A row shows a checkbox-style circle, name,
  company, the first line of the latest note, and on the right the state badge
  ("vor 3 Wochen", "überfällig seit 12 Tagen", "Geburtstag in 4 Tagen").
  Clicking the circle opens **Kontakt eintragen** for that person. Clicking the
  row selects it.
- **Right pane:** the person. Header with name, company and role, tags as
  chips, phone (tel: link) and email (mailto: link), city, how we met, profile
  note. A prominent **Kontakt eintragen** button. Then: Zuletzt besprochen
  (the history, latest first, each with date, kind and note), Angehörige,
  Stichtage, Intervall and next date, Archivieren. Everything edits inline.
- **Kontakt eintragen** (sheet over the right pane): kind as a segmented
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
recogniser in Safari on Mac and iPhone. A language toggle (de-DE / en-US)
sits on the button; the choice is a user setting.

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
  `faellig_am`, with a `VALARM` the morning of. People with state `unbekannt`
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
- **WP2 Kontakte und Fälligkeit.** Kontakt eintragen, history, due logic
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
Docker image and compose file with a TLS proxy · server-side dictation
(Parakeet v3 sidecar) · vCard import with a review screen · sharing a person
between users · email digest · Apple Contacts or LinkedIn integration (not
planned).

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
- **Row badge ("Plakette").** `unbekannt` → "noch kein Kontakt"; `erkaltet` →
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
- **Kontakt eintragen.** Any day up to and including today in the user's time
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
  person, keeps tag and search, drops `filter` (Noch kein Kontakt / Archiv hold
  nobody that a card could count). Clicking a sidebar entry resets the card. In
  the Archiv `karte` is ignored. The counts are always over all active people,
  whatever tag, search or card is open; opening a person or saving keeps the card
  in the URL. Empty card lists have their own sentence.
- **Sort order** with a card open follows §6 (erkaltet first, then `faellig_am`,
  then name); every other list stays by name. Cards, rows and the Personenseite
  all read the same `faelligkeit.bindungen()` result for the request: one query
  for all of a user's people, state and sorting in Python (a few hundred people).
- **Personenseite** now has two forms (name, company, role, contact links; then
  the other fields) with the button "Kontakt eintragen" and "Zuletzt besprochen"
  between them, because HTML has no nested forms. Both save on `change` as
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
  `unbekannt`: one all-day event on `max(faellig_am, heute)` (overdue and cold
  people on today, never in the past), moving with the same UID when a Kontakt is
  logged. Description "Zuletzt besprochen: <first line of the latest real note>"
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

