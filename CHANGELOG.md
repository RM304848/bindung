# Änderungen

Hier steht, was sich für die Menschen ändert, die Bindung benutzen. Jeder
Release bekommt einen eigenen Abschnitt, geschrieben vor dem Taggen.

## Unveröffentlicht

## 0.1.1 (2026-11-12)

Erste Rückmeldungen aus dem Alltag: klarere Worte, die Profilnotiz gleich oben, Hell oder Dunkel nach eigener Wahl. Die Datenbank wird beim ersten Start erweitert, alle Daten bleiben erhalten.

- **„Touchpoint“ statt „Kontakt“.** „Kontakt eintragen“ klang, als legtest du
  einen Eintrag im Telefonbuch an. Der Knopf und das Blatt heißen jetzt
  **Touchpoint eintragen**, in der Seitenleiste steht **Noch kein Touchpoint**,
  auf der Personenseite **Letzter Touchpoint**, und in der Liste steht
  „noch kein Touchpoint“. Gemeint ist weiter dasselbe: ein Gespräch, ein Anruf,
  ein Treffen mit Art, Datum und Notiz. „Zuletzt besprochen“ heißt wie zuvor.
  Alles, was du schon eingetragen hast, bleibt unverändert.
- **Profilnotiz gleich unter dem Kopf der Person.** Auf der Personenseite
  stehen jetzt zuerst Name, Firma und Rolle, die Tags, Telefon und E-Mail, Ort
  und Herkunft und die **Profilnotiz**, dann der Knopf „Touchpoint eintragen“
  mit „Zuletzt besprochen“, „Angehörige“ und „Stichtage“, ganz unten Intervall,
  Nächster Termin und Archivieren. Unter der Profilnotiz steht ein Hinweis:
  Sie wird beim Verlassen des Feldes gespeichert.
- **Hell oder Dunkel selbst wählen.** Unter Einstellungen gibt es den neuen
  Abschnitt **Darstellung** mit „System“, „Hell“ und „Dunkel“. „System“ folgt
  wie bisher deinem Gerät; mit „Hell“ oder „Dunkel“ bleibt Bindung dabei, auch
  wenn dein Mac anders eingestellt ist. Die Wahl gilt sofort und gehört zu
  deinem Zugang, nicht zum Gerät. Die Anmeldeseite folgt immer dem Gerät.
  Beim ersten Start nach dem Update wird die Datenbank um diese Einstellung
  erweitert, deine Daten bleiben erhalten.
- **Verknüpfen mit vorbelegter Suche.** Beim Verknüpfen eines Angehörigen ist
  die Personensuche mit seinem Namen vorbelegt, und die passenden Personen
  stehen sofort da, ohne dass du tippen musst. Du kannst den Namen im Feld
  weiter ändern.

## 0.1.0 (2026-11-11)

Das erste Release: Bindung merkt sich, worüber du zuletzt mit jemandem gesprochen hast, und erinnert dich, bevor eine Bindung erkaltet.

Du legst die Menschen an, die dir wichtig sind, trägst nach jedem Gespräch einen
Kontakt ein und siehst auf einen Blick, wer sich über ein Lebenszeichen freuen
würde. Alles, was du einträgst, bleibt auf deinem eigenen Rechner oder Server.
Es gibt keine künstliche Intelligenz im Hintergrund: Wer fällig ist und was die
Tagesmeldung sagt, folgt festen, nachvollziehbaren Regeln.

### Der Überblick

- **Drei Spalten wie in Erinnerungen.** Links die Seitenleiste (Alle, Noch kein
  Kontakt, Archiv und deine Tags), in der Mitte die Liste mit den drei Karten
  „Braucht Aufmerksamkeit“, „Erkaltet“ und „Diese Woche“ und der Suche, rechts
  die Seite der Person. Hell und Dunkel folgen der Einstellung deines Geräts.
- **Auch auf dem Telefon.** Dort ist immer eine Spalte offen: Seitenleiste,
  Liste oder Person, mit „‹ Zurück“ zur vorigen. Die Adresse im Browser merkt
  sich Filter, Suche und die offene Person; Neuladen und die Zurück-Taste führen
  an dieselbe Stelle. Die Bedienelemente sind so groß, dass du sie mit dem Daumen
  triffst.
- **Suche.** Das Suchfeld über der Liste filtert beim Tippen nach Name, Firma,
  Ort und Tag, ohne auf Groß- und Kleinschreibung zu achten. Die offene Person
  bleibt dabei offen.

### Personen und Tags

- **Personen anlegen und bearbeiten.** Mit „Person hinzufügen“ legst du eine
  Person an: Name, Firma, Rolle, Telefon, E-Mail, Ort, Herkunft und
  Profilnotiz. Auf der Personenseite bearbeitest du alles direkt am Feld; beim
  Verlassen des Feldes wird gespeichert („Gespeichert“ erscheint oben).
  Telefon und E-Mail sind Links zum Anrufen und Schreiben.
- **Mehrere hinzufügen.** Ein Name pro Zeile (oder „Name; Firma“), dazu Tags
  für alle und eine grobe Angabe, wann ihr zuletzt gesprochen habt: „Diesen
  Monat“, „Vor ein paar Monaten“, „Über ein Jahr her“ oder „Unbekannt“. So
  kommen die ersten Leute in einer Sitzung in die App; doppelte Namen und leere
  Zeilen werden übersprungen. „Vor ein paar Monaten“ meint rund drei Monate:
  Die Leute starten als „überfällig“, nicht schon als „erkaltet“ – du meldest
  dich bald bei ihnen, statt sie als verloren zu führen.
- **Tags.** Mit „Tag hinzufügen“ in der Seitenleiste legst du Tags an; jeder
  hat seine eigene Liste mit Zähler. Auf der Personenseite wählst du die Tags
  einer Person als Chips an oder ab oder legst dort gleich einen neuen an. In
  der Liste eines Tags kannst du ihn mit „Tag bearbeiten“ umbenennen oder
  löschen – die Personen bleiben dabei erhalten.
- **Noch kein Kontakt und Archiv.** „Noch kein Kontakt“ zeigt, wen du noch gar
  nicht eingetragen hast. „Archivieren“ nimmt eine Person aus allen Listen,
  im „Archiv“ holst du sie mit „Wiederherstellen“ zurück.

### Kontakte eintragen und nachlesen

- **Kontakt eintragen.** Nach einem Gespräch tippst du in der Liste auf den
  Kreis vor der Person oder auf der Personenseite auf „Kontakt eintragen“. Es
  öffnet sich ein Blatt: die Art (Anruf, Nachricht, E-Mail, Treffen,
  Sonstiges), das Datum (heute vorbelegt, nie in der Zukunft) und eine Notiz.
  Mit „Speichern“ stehen Zeile, Zähler und Karten sofort richtig da, ohne dass
  die Seite neu lädt. Ein „Nächster Termin“, den du gesetzt hattest, ist damit
  erledigt und wird gelöscht.
- **Zuletzt besprochen.** Die Personenseite zeigt alle Kontakte, den jüngsten
  zuerst, mit Datum, Art und Notiz – das, was du vor dem nächsten Anruf liest.
  Eine grobe Angabe aus „Mehrere hinzufügen“ erscheint als „Schätzung“. Mit
  „Bearbeiten“ korrigierst du einen Eintrag an Ort und Stelle, „Löschen“
  fragt vorher nach.
- **Diktat.** In jedem Notizfeld – „Notiz“ beim Kontakt eintragen und beim
  Bearbeiten eines Eintrags, „Profilnotiz“, „Namen, einer pro Zeile“ bei
  „Mehrere hinzufügen“ – steht unter dem Feld rechts ein Mikrofonknopf. Ein Tipp
  startet das Diktat, der Knopf leuchtet orange und pulsiert, ein zweiter Tipp
  („Diktat beenden“) oder die Escape-Taste beendet es. Was du sprichst, erscheint
  grau neben dem Knopf und kommt als Text ins Feld, sobald der Browser sicher ist:
  an die Stelle des Cursors, sonst ans Ende. Auf der Personenseite wird die Notiz
  danach gespeichert wie nach jeder Eingabe. Es läuft immer nur ein Diktat. Geht
  etwas schief (Mikrofon nicht erlaubt, nichts gehört, keine Verbindung, kein
  Mikrofon), steht ein kurzer Satz unter dem Feld. Das Diktat braucht **Safari oder
  Chrome**; in Browsern ohne Spracherkennung (Firefox) gibt es den Knopf nicht. Beim
  ersten Mal fragt der Browser nach dem Mikrofon. Die Sprache (Deutsch oder
  Englisch) stellst du unter „Einstellungen › Diktat“ ein; sie gilt ab dem nächsten
  Laden der Seite. **Gut zu wissen:** Die Erkennung macht der Browser, nicht Bindung;
  das Audio geht dabei an den Spracherkennungsdienst von Apple (Safari) oder Google
  (Chrome), nicht an deinen Server. Wer das nicht will, diktiert mit einer
  Diktier-App auf dem Mac, die in jedem Textfeld funktioniert, auch in Bindung.

### Wer sich melden sollte

- **Der Zustand jeder Person.** „Noch kein Kontakt“, „vor 3 Wochen“, „fällig in
  4 Tagen“, „überfällig seit 12 Tagen“ oder „erkaltet“. Er steht rechts in der
  Zeile und färbt den Kreis; der Zeilentext zeigt die erste Zeile der letzten
  Notiz (die Profilnotiz nur, solange es noch kein Gespräch gibt). Erkaltet ist,
  wer länger als das Doppelte seines Intervalls, höchstens aber 180 Tage, nicht
  gesprochen wurde.
- **Intervall und Fälligkeit.** „Intervall in Tagen“ gilt für die Person (leer:
  deine Vorgabe von 56 Tagen), „Nächster Termin“ ersetzt es ein Mal. Unter
  beiden zeigt die Personenseite Zustand, letzten Kontakt und „Fällig am“.
- **Karten filtern.** Ein Klick auf „Braucht Aufmerksamkeit“, „Erkaltet“ oder
  „Diese Woche“ filtert die Liste, mit den Erkalteten zuerst, dann nach
  Fälligkeit. Ein zweiter Klick auf dieselbe Karte hebt den Filter auf. Die
  Zahlen zählen immer alle aktiven Personen; der Filter wirkt zusammen mit
  Tag und Suche und steht in der Adresse.

### Angehörige und Stichtage

- **Angehörige.** Auf der Personenseite steht unter „Zuletzt besprochen“ der
  Abschnitt „Angehörige“: Name, Rolle (Partner/in, Kind, Elternteil,
  Geschwister oder „Sonstiges“ mit eigenem Wort, zum Beispiel Patenkind) und
  auf Wunsch der Geburtstag. Mit „Angehörigen hinzufügen“ trägst du jemanden
  ein; „Bearbeiten“ ändert den Eintrag an Ort und Stelle, „Löschen“ fragt vorher
  nach.
- **Angehörige mit einer Person in der App verknüpfen.** Ist ein Angehöriger
  selbst eine Person in Bindung, wählst du sie beim Hinzufügen unter „In der
  App“ oder später mit „Verknüpfen“ aus (Suche nach dem Namen). Bei der anderen
  Person entsteht dann der Eintrag mit der umgekehrten Rolle: Ist Ben für Anna
  ein Kind, ist Anna bei Ben ein Elternteil. Diese Rolle lässt sich bei Ben
  getrennt ändern. Der Name führt per Klick zur anderen Personenseite.
  „Verknüpfung lösen“ und „Löschen“ entfernen auch den Eintrag auf der anderen
  Seite; die Rückfrage sagt vorher, was verschwindet.
- **Stichtage.** Unter den Angehörigen steht „Stichtage“: Geburtstage,
  Jahrestage oder benannte Tage, mit oder ohne Jahr („24. März“, „24. März
  1986“). Zu jedem steht, wann er das nächste Mal ist („in 12 Tagen“, „heute“),
  und, wenn das Jahr bekannt ist, wie alt oder wie viele Jahre („wird 40“, „10
  Jahre“). Mit „Stichtag hinzufügen“ legst du einen an; der „Vorlauf in Tagen“
  ersetzt für diesen Tag deine Vorgabe von 7 Tagen. Der Geburtstag eines
  Angehörigen erscheint hier von selbst und wird bei den Angehörigen
  geändert.
- **Stichtage in der Liste.** Liegt ein Stichtag im Vorlauf, steht die Person
  unter „Diese Woche“, und ihre Zeile bekommt eine zweite, grün gerahmte
  Plakette neben dem Zustand: „Geburtstag in 4 Tagen“, „Jahrestag heute“. Ihr
  Zustand (zum Beispiel „überfällig“) bleibt dabei, wie er ist.

### Erinnert werden

- **Tagesmeldung.** Einmal am Tag, zu der Uhrzeit aus „Einstellungen ›
  Erinnern“ (in deiner Zeitzone), schaut Bindung nach, ob jemand wartet:
  überfällige und erkaltete Personen, dazu wer heute fällig wird, und
  Stichtage, die heute sind oder in ihrem Vorlauf liegen. Gibt es etwas, kommt
  eine Mitteilung, zum Beispiel „3 Personen warten · 1 Geburtstag“ mit bis zu
  drei Namen und dem nächsten Stichtag („Geburtstag Mia Beispiel in 3 Tagen“),
  mit dem Symbol von Bindung. Ein Klick öffnet Bindung bei „Braucht
  Aufmerksamkeit“, oder bei „Diese Woche“, wenn nur Stichtage anstehen. Gibt es
  nichts, kommt auch nichts. Ein Tag, an dem Bindung nicht lief, wird nicht
  nachgeholt; war es erst nach der Uhrzeit wieder da, kommt die Meldung noch am
  selben Tag. **Bindung muss dafür laufen.**
- **Benachrichtigungen einschalten.** Unter „Einstellungen › Benachrichtigungen“
  wählst du „In diesem Browser aktivieren“ und erlaubst Mitteilungen; „Testmeldung
  senden“ zeigt sofort, ob es klappt. Das geht für jeden Browser und jedes Gerät
  einzeln, mit „Deaktivieren“ nimmst du einen wieder heraus. **Safari auf dem Mac**
  kann Mitteilungen erst, wenn Bindung im Dock liegt (Ablage › Zum Dock
  hinzufügen); auf dem iPhone muss Bindung auf dem Startbildschirm liegen.
- **Hinweis in der App.** Hat ein Browser keine Mitteilungen (nicht erlaubt oder
  nicht möglich), zeigt Bindung die Tagesmeldung oben als Streifen, einmal am Tag.
  „Heute ausblenden“ schließt ihn bis morgen; „Benachrichtigungen erlauben“ fragt
  den Browser. Wer Mitteilungen eingeschaltet hat, sieht den Streifen nicht.
- **Kalender abonnieren.** Unter „Einstellungen › Kalender“ stehen zwei
  Kalenderadressen (webcal und https bzw. http) mit „Kopieren“. In Apple
  Kalender wählst du Ablage › Neues Kalenderabonnement, fügst die Adresse ein und
  stellst die Aktualisierung auf stündlich. Im Kalender stehen alle Stichtage
  deiner Personen als jährlich wiederkehrende Tage („Geburtstag Anna Beispiel“,
  „Anna Beispiel: Firmenjubiläum“, ein Kindergeburtstag mit dem Namen der Eltern)
  und je Person, bei der du schon einmal Kontakt eingetragen hast, ein Termin
  „Melden bei …“ am Tag, an dem du dich melden wolltest, mit einer Erinnerung um
  9 Uhr und der ersten Zeile der letzten Notiz. Wer überfällig oder erkaltet ist,
  steht am nächsten Sonntag im Kalender, dem Tag der Wochendurchsicht, nicht
  jeden Morgen neu. Alle Einträge sind ganztägig und als „frei“ eingetragen,
  blockieren also nichts. Trägst du einen Kontakt ein, rückt der Termin weiter.
  Archivierte Personen und Personen ohne Kontakt kommen nicht vor. Wer eine Datei
  statt eines Abos will, nimmt „Herunterladen“. Stichtage am 29. Februar stehen im
  Kalender nur in Schaltjahren am 29.; wie dein Kalender die anderen Jahre
  behandelt, entscheidet er selbst. Bei einem bekannten Jahr steht „Geburtsjahr
  1986“ bzw. „Seit 2012“ in der Beschreibung, kein Alter: das würde im nächsten
  Jahr nicht mehr stimmen.
- **Adresse neu erzeugen.** Wer die Kalenderadresse kennt, sieht deine
  Stichtage und wen du anrufen willst. Ist sie in falsche Hände geraten, erzeugst
  du unter „Einstellungen › Kalender“ eine neue (nach einer Rückfrage); die alte
  funktioniert dann nicht mehr, und du trägst die neue in deinen Kalendern ein.

### Bindung auf dem Mac und auf dem Telefon

- **Mac-App.** Das Disk-Image „Bindung-0.1.0-mac.dmg“ enthält die App „Bindung“;
  du ziehst sie in „Programme“. Ein Doppelklick startet Bindung ohne Terminal: Es
  erscheint ein Symbol aus zwei Ringen in der Menüleiste (kein Symbol im Dock) und
  Bindung öffnet sich im Browser unter http://127.0.0.1:8788. Das Menü des Symbols
  hat „Bindung öffnen“, „Datenordner zeigen“ und „Beenden“; „Beenden“ steht
  auch unten in der Seitenleiste, neben „Abmelden“. Solange die App läuft,
  kommt die Tagesmeldung. Die App ist nicht signiert: ein heruntergeladenes
  Image öffnest du beim ersten Mal mit Rechtsklick › „Öffnen“.
- **Erster Start.** Beim ersten Start gibt es noch niemanden: Bindung fragt nach
  einem Namen und einem Passwort (zweimal, mindestens 8 Zeichen) und meldet dich
  gleich an. Danach ist diese Seite zu; weitere Nutzer legst du wie bisher mit
  `bindung nutzer anlegen` an.
- **Auf dem Startbildschirm.** Bindung lässt sich wie eine App auf den
  Startbildschirm legen (Safari: Teilen › „Zum Home-Bildschirm“) und öffnet sich
  dann ohne Adressleiste, mit eigenem Symbol und Namen. Das Telefon muss Bindung
  dafür erreichen können: die Mac-App hört nur auf diesem Mac, ein Server, den du
  mit `BINDUNG_HOST` nach außen öffnest, ist auch vom Telefon erreichbar.
  Mitteilungen auf dem iPhone setzen eine verschlüsselte Adresse (https) voraus.
- **Symbol.** Bindung hat ein eigenes Symbol: zwei ineinandergreifende Ringe, im
  Browser-Tab, auf dem Startbildschirm, in der Menüleiste und in Mitteilungen.

### Anmeldung, Einstellungen und deine Daten

- **Anmeldung.** Bindung ist eine Web-App mit eigener Anmeldung: jeder Nutzer
  sieht nur seine eigenen Einträge. Auf einem Server legst du Nutzer mit
  `bindung nutzer anlegen <name>` an (das Passwort wird zweimal abgefragt und
  bleibt dabei unsichtbar); `bindung nutzer passwort <name>` setzt ein neues,
  `bindung nutzer liste` zeigt alle.
- **Angemeldet bleiben.** Die Sitzung hält 30 Tage ohne Benutzung und
  verlängert sich beim Benutzen, höchstens einmal am Tag. Nach falschen
  Anmeldeversuchen muss man mit jedem Versuch länger warten. Abmelden geht unten
  in der Seitenleiste.
- **Einstellungen.** Unten in der Seitenleiste öffnet „Einstellungen“ eine
  eigene Seite, mit „‹ Zurück“ geht es zurück. Jeder Abschnitt hat seinen
  eigenen Knopf und meldet „Gespeichert“:
  - **Erinnern:** dein Intervall in Tagen (Vorgabe für alle Personen ohne
    eigenes), der Vorlauf für Stichtage, die Zeitzone und die Uhrzeit der
    Tagesmeldung.
  - **Benachrichtigungen:** ob dieser Browser Mitteilungen bekommt, wie viele
    Browser angemeldet sind, und „Testmeldung senden“.
  - **Kalender:** deine Kalenderadresse.
  - **Diktat:** die Sprache, in der du in Notizfelder sprichst
    (Deutsch oder Englisch).
  - **Passwort ändern:** aktuelles Passwort, dann zweimal das neue. Du bleibst
    angemeldet; alle anderen Geräte werden abgemeldet.
- **Datenordner.** Alles, was du einträgst, liegt in einem einzigen Ordner
  (auf dem Mac `~/Library/Application Support/Bindung`). `bindung ort` zeigt,
  wo er ist; mit der Umgebungsvariable `BINDUNG_DATEN` lässt er sich umstellen.
  Die Datenbank wird beim ersten Start angelegt und bei Updates erweitert, deine
  Einträge bleiben dabei erhalten.
- **Start im Terminal.** `bindung serve` startet Bindung auf
  http://127.0.0.1:8785, `bindung app` startet es wie die Mac-App. Mit
  `BINDUNG_HOST` und `BINDUNG_PORT` (oder `--host` und `--port`) lässt sich
  Adresse und Port ändern; steht ein Server mit Verschlüsselung (https) davor,
  sorgt `BINDUNG_SICHER=1` dafür, dass das Anmelde-Cookie nur verschlüsselt
  geschickt wird.
- **Updates kommen sicher an.** Nach einem Update lädt der Browser Aussehen und
  Skripte der App garantiert neu, statt tagelang eine alte Fassung aus seinem
  Zwischenspeicher zu zeigen.

### Behoben

- Die Suche behält die offene Person: nach dem Suchen und Neuladen ist sie
  noch da.
- „Braucht Aufmerksamkeit“ auf den Karten bricht auf dem Telefon nicht mehr
  mitten im Wort um.
