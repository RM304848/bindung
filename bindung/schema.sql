-- Das Schema von Bindung (PLAN.md, Abschnitt 5; Begriffe aus CONTEXT.md).
--
-- Jede Tabelle mit Nutzerdaten traegt `nutzer_id`, jede Abfrage filtert danach;
-- es gibt keine Sicht ueber Nutzer hinweg.
--
-- Zeiten sind UTC als ISO-Text (`2026-09-23T22:00:00Z`). Tage sind ISO-Tage in
-- der Zeitzone des Nutzers (`2026-09-24`). Ein Jahrestag mit oder ohne Jahr
-- steht als `YYYY-MM-DD` bzw. `--MM-DD` (ISO 8601, wie vCard).
--
-- Abgeleitetes -- Zustand, Faelligkeit, Zaehler der Karten -- steht hier NICHT;
-- es wird beim Lesen gerechnet (PLAN.md, Abschnitt 6).
--
-- Eine spaetere Aenderung kommt als Eintrag in `db.MIGRATIONEN`, nicht hier.

CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS nutzer (
    id                    INTEGER PRIMARY KEY,
    name                  TEXT    NOT NULL UNIQUE COLLATE NOCASE,
    -- `scrypt$n$r$p$salz$hash` (auth.py); das Salz ist je Nutzer eigen.
    passwort_hash         TEXT    NOT NULL,
    -- Einstellungen
    tagesmeldung_zeit     TEXT    NOT NULL DEFAULT '08:00'
                          CHECK (tagesmeldung_zeit GLOB '[0-2][0-9]:[0-5][0-9]'),
    zeitzone              TEXT    NOT NULL DEFAULT 'Europe/Berlin',
    vorgabe_intervall_tage INTEGER NOT NULL DEFAULT 56 CHECK (vorgabe_intervall_tage > 0),
    vorgabe_vorlauf_tage  INTEGER NOT NULL DEFAULT 7 CHECK (vorgabe_vorlauf_tage >= 0),
    -- Die geheime Kalenderadresse: /kalender/<kalender_token>.ics
    kalender_token        TEXT    NOT NULL UNIQUE,
    diktat_sprache        TEXT    NOT NULL DEFAULT 'de-DE',
    erstellt_am           TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE TABLE IF NOT EXISTS sitzung (
    id             INTEGER PRIMARY KEY,
    nutzer_id      INTEGER NOT NULL REFERENCES nutzer (id) ON DELETE CASCADE,
    -- SHA-256 des Tokens im Cookie: die Datenbank hat nie den Token selbst.
    token_hash     TEXT    NOT NULL UNIQUE,
    erstellt_am    TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    laeuft_ab_am   TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sitzung_nutzer ON sitzung (nutzer_id);

CREATE TABLE IF NOT EXISTS person (
    id              INTEGER PRIMARY KEY,
    nutzer_id       INTEGER NOT NULL REFERENCES nutzer (id) ON DELETE CASCADE,
    name            TEXT    NOT NULL,
    firma           TEXT,
    rolle           TEXT,
    telefon         TEXT,
    email           TEXT,
    ort             TEXT,
    herkunft        TEXT,
    profilnotiz     TEXT,
    -- NULL: Vorgabe des Nutzers
    intervall_tage  INTEGER CHECK (intervall_tage IS NULL OR intervall_tage > 0),
    -- Naechster Termin: ein ISO-Tag, der fuer ein Mal das Intervall ersetzt.
    naechster_termin TEXT,
    archiviert_am   TEXT,
    erstellt_am     TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
CREATE INDEX IF NOT EXISTS idx_person_nutzer ON person (nutzer_id, archiviert_am);

CREATE TABLE IF NOT EXISTS tag (
    id          INTEGER PRIMARY KEY,
    nutzer_id   INTEGER NOT NULL REFERENCES nutzer (id) ON DELETE CASCADE,
    name        TEXT    NOT NULL COLLATE NOCASE,
    reihenfolge INTEGER NOT NULL DEFAULT 0,
    UNIQUE (nutzer_id, name)
);

CREATE TABLE IF NOT EXISTS person_tag (
    nutzer_id  INTEGER NOT NULL REFERENCES nutzer (id) ON DELETE CASCADE,
    person_id  INTEGER NOT NULL REFERENCES person (id) ON DELETE CASCADE,
    tag_id     INTEGER NOT NULL REFERENCES tag (id) ON DELETE CASCADE,
    PRIMARY KEY (person_id, tag_id)
);
CREATE INDEX IF NOT EXISTS idx_person_tag_tag ON person_tag (tag_id);

CREATE TABLE IF NOT EXISTS kontakt (
    id          INTEGER PRIMARY KEY,
    nutzer_id   INTEGER NOT NULL REFERENCES nutzer (id) ON DELETE CASCADE,
    person_id   INTEGER NOT NULL REFERENCES person (id) ON DELETE CASCADE,
    datum       TEXT    NOT NULL,
    art         TEXT    NOT NULL
                CHECK (art IN ('anruf', 'nachricht', 'email', 'treffen', 'sonstiges',
                               'schaetzung')),
    notiz       TEXT,
    erstellt_am TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
CREATE INDEX IF NOT EXISTS idx_kontakt_person ON kontakt (person_id, datum);

CREATE TABLE IF NOT EXISTS angehoeriger (
    id                   INTEGER PRIMARY KEY,
    nutzer_id            INTEGER NOT NULL REFERENCES nutzer (id) ON DELETE CASCADE,
    person_id            INTEGER NOT NULL REFERENCES person (id) ON DELETE CASCADE,
    name                 TEXT    NOT NULL,
    rolle                TEXT    NOT NULL
                         CHECK (rolle IN ('partner', 'kind', 'elternteil', 'geschwister',
                                          'sonstiges')),
    -- Freitext zur Rolle, vor allem bei 'sonstiges'
    rolle_text           TEXT,
    -- `YYYY-MM-DD` oder `--MM-DD`
    geburtstag           TEXT,
    -- Verknuepfung: die Person in der App, und das Gegenstueck auf deren Seite
    verknuepfte_person_id INTEGER REFERENCES person (id) ON DELETE SET NULL,
    gegenstueck_id       INTEGER REFERENCES angehoeriger (id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_angehoeriger_person ON angehoeriger (person_id);

CREATE TABLE IF NOT EXISTS stichtag (
    id             INTEGER PRIMARY KEY,
    nutzer_id      INTEGER NOT NULL REFERENCES nutzer (id) ON DELETE CASCADE,
    person_id      INTEGER NOT NULL REFERENCES person (id) ON DELETE CASCADE,
    bezeichnung    TEXT    NOT NULL,
    art            TEXT    NOT NULL CHECK (art IN ('geburtstag', 'jahrestag', 'sonstiges')),
    -- `YYYY-MM-DD` oder `--MM-DD` (ohne Jahr)
    datum          TEXT    NOT NULL,
    -- NULL: Vorgabe des Nutzers
    vorlauf_tage   INTEGER CHECK (vorlauf_tage IS NULL OR vorlauf_tage >= 0),
    -- Der Geburtstag eines Angehoerigen gehoert zu dessen Eintrag.
    angehoeriger_id INTEGER REFERENCES angehoeriger (id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_stichtag_person ON stichtag (person_id);

CREATE TABLE IF NOT EXISTS push_abo (
    id          INTEGER PRIMARY KEY,
    nutzer_id   INTEGER NOT NULL REFERENCES nutzer (id) ON DELETE CASCADE,
    endpunkt    TEXT    NOT NULL UNIQUE,
    schluessel_p256dh TEXT NOT NULL,
    schluessel_auth   TEXT NOT NULL,
    erstellt_am TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
CREATE INDEX IF NOT EXISTS idx_push_abo_nutzer ON push_abo (nutzer_id);

-- Je Nutzer eine Zeile: an welchem Tag (in seiner Zeitzone) die Tagesmeldung
-- zuletzt rausging, und an welchem er den Hinweis in der App weggeklickt hat.
CREATE TABLE IF NOT EXISTS digest_protokoll (
    nutzer_id            INTEGER PRIMARY KEY REFERENCES nutzer (id) ON DELETE CASCADE,
    letzter_versand_am   TEXT,
    hinweis_weggeklickt_am TEXT
);
