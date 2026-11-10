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
  approximate date (today −15, −120, −400 days) and no note, so the due logic
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
