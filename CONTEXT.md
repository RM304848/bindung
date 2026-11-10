# Bindung

Ein Mensch hält die Verbindung zu den Menschen, die ihm wichtig sind: Er weiß,
worüber er zuletzt mit ihnen gesprochen hat, und wird erinnert, bevor eine
Bindung erkaltet. Die App kennt nur die Begriffe unten. Wer die Menschen sind
und was sie erzählt haben, sind Einträge und Notizen des Nutzers, kein Text der
App.

## Nutzer

**Nutzer**:
Die Person, die sich anmeldet; alles, was sie einträgt, sieht nur sie.
_Avoid_: Account, Benutzer, Mitglied

**Sitzung**:
Eine Anmeldung in einem Browser, gültig bis zum Abmelden oder bis sie abläuft.
_Avoid_: Session, Token (als Nutzerbegriff), Login

**Einstellungen**:
Die Vorgaben eines Nutzers: Passwort, Uhrzeit der Tagesmeldung, Vorgabe-Intervall, Vorgabe-Vorlauf, Zeitzone, Kalenderadresse, Diktatsprache.
_Avoid_: Profil, Konfiguration, Settings

## Menschen

**Person**:
Ein Mensch, zu dem der Nutzer die Bindung halten will, mit Name, Firma, Rolle, Kontaktdaten, Herkunft der Bekanntschaft und Profilnotiz.
_Avoid_: Kontakt (für den Menschen), Eintrag, Connection, Freund

**Bindung**:
Die Verbindung zwischen Nutzer und Person, so wie die App sie sieht: ihr Zustand, ihr Intervall, ihr nächster Termin.
_Avoid_: Beziehung, Relationship, Verhältnis

**Tag**:
Ein vom Nutzer benanntes Etikett an einer Person; eine Person trägt beliebig viele, die Seitenleiste zeigt je Tag eine Liste.
_Avoid_: Kreis, Kategorie, Gruppe, Liste (als Datenbegriff)

**Profilnotiz**:
Ein Freitext an der Person, der bleibt: wer sie ist, was sie mag, was man wissen muss.
_Avoid_: Beschreibung, Bio, Notiz (ohne Zusatz)

**Herkunft**:
Wie und wo Nutzer und Person sich kennengelernt haben.
_Avoid_: Quelle, Kontext, Ursprung

**Archiv**:
Wohin eine Person geht, der der Nutzer nicht mehr nachgehen will; sie bleibt mit ihrer Geschichte da und kann zurückgeholt werden.
_Avoid_: Löschen, Papierkorb, Inaktiv

## Angehörige

**Angehöriger**:
Ein Mensch aus dem Umfeld einer Person, mit Name und Rolle, mit oder ohne Geburtstag, mit oder ohne Verknüpfung zu einer anderen Person in der App.
_Avoid_: Familienmitglied, Verwandter, Relation

**Rolle** (eines Angehörigen):
Was der Angehörige für die Person ist: Partner/in, Kind, Elternteil, Geschwister, Sonstiges mit Freitext.
_Avoid_: Beziehungstyp, Typ, Art (für Angehörige)

**Verknüpfung**:
Die Verbindung eines Angehörigen mit einer Person in der App; sie erzeugt auf der anderen Seite das Gegenstück mit der umgekehrten Rolle.
_Avoid_: Link, Referenz, Zuordnung

**Gegenstück**:
Der Angehörigen-Eintrag auf der anderen Seite einer Verknüpfung; seine Rolle ist eigenständig bearbeitbar.
_Avoid_: Inverse, Spiegel, Rückverweis

## Kontakte und Fälligkeit

**Kontakt**:
Ein Austausch mit einer Person an einem Datum, mit Art und Notiz; er wird nie überschrieben, nur ergänzt.
_Avoid_: Interaktion, Log, Eintrag, Gespräch (als Datenbegriff)

**Art** (eines Kontakts):
Wie der Austausch stattfand: Anruf, Nachricht, E-Mail, Treffen, Sonstiges; Schätzung für einen groben letzten Kontakt ohne Notiz.
_Avoid_: Kanal, Methode, Medium

**Zuletzt besprochen**:
Die Kontakte einer Person, jüngster zuerst; das, was der Nutzer vor dem nächsten Anruf liest.
_Avoid_: Historie, Verlauf, Timeline

**Schätzung**:
Ein Kontakt ohne Notiz mit ungefährem Datum, den der Nutzer setzt, wenn er nur grob weiß, wann er die Person zuletzt gesprochen hat.
_Avoid_: Platzhalter, Dummy, Startwert

**Letzter Kontakt**:
Das Datum des jüngsten Kontakts einer Person; fehlt er, ist der Zustand unbekannt.
_Avoid_: Last contact, Letzte Interaktion

**Intervall**:
Wie viele Tage nach dem letzten Kontakt der Nutzer sich wieder melden will; je Person einstellbar, sonst die Vorgabe des Nutzers (56 Tage).
_Avoid_: Frequenz, Rhythmus, Cadence, Zyklus

**Nächster Termin**:
Ein vom Nutzer gesetztes Datum, das für ein Mal das Intervall ersetzt; der nächste Kontakt löscht es.
_Avoid_: Snooze, Wiedervorlage, Override

**Fällig am**:
Der Tag, an dem die App den Nutzer an eine Person erinnert: der nächste Termin, sonst letzter Kontakt plus Intervall.
_Avoid_: Deadline, Frist, Due date

**Zustand** (einer Bindung):
Genau eines von: unbekannt, ok, bald, überfällig, erkaltet.
_Avoid_: Status, Ampel, Health

**Unbekannt**:
Der Zustand einer Person ohne Kontakt; sie zählt auf keiner Karte.
_Avoid_: Neu, Leer, Offen

**Bald**:
Der Zustand einer Person, die in den nächsten sieben Tagen fällig wird.
_Avoid_: Demnächst, Upcoming, Anstehend

**Überfällig**:
Der Zustand einer Person, deren Fälligkeit vorbei ist, die aber noch nicht erkaltet ist.
_Avoid_: Braucht Aufmerksamkeit (als Zustand), Verspätet, Overdue

**Erkaltet**:
Der Zustand einer Person, deren letzter Kontakt länger her ist als das Doppelte ihres Intervalls oder 180 Tage, je nachdem, was früher eintritt.
_Avoid_: Kalt, Cold, Verloren, Eingeschlafen

## Stichtage

**Stichtag**:
Ein jährlich wiederkehrender Tag an einer Person: Geburtstag, Jahrestag oder ein benannter Tag; mit oder ohne Jahr.
_Avoid_: Event, Ereignis, Termin (für Jahrestage), Wichtiges Datum

**Vorlauf**:
Wie viele Tage vor einem Stichtag er in der App erscheint; je Stichtag einstellbar, sonst die Vorgabe des Nutzers (7 Tage).
_Avoid_: Lead time, Erinnerung, Vorwarnung

## Oberfläche

**Seitenleiste**:
Die linke Spalte mit Alle, Noch kein Kontakt, Archiv und einer Liste je Tag.
_Avoid_: Navigation, Menü, Sidebar

**Liste**:
Die mittlere Spalte mit den Karten, der Suche und den Personen.
_Avoid_: Übersicht, Tabelle, Feed

**Karte**:
Eine der drei Zahlen über der Liste: Braucht Aufmerksamkeit, Erkaltet, Diese Woche; ein Klick filtert die Liste.
_Avoid_: Kachel, Widget, Metrik, Dashboard

**Braucht Aufmerksamkeit**:
Die Karte mit allen überfälligen und erkalteten Personen.
_Avoid_: Needs attention, Handlungsbedarf, Offen

**Diese Woche**:
Die Karte mit den Personen, die bald fällig sind oder deren Stichtag im Vorlauf liegt; die Grundlage der wöchentlichen Durchsicht.
_Avoid_: Upcoming, Demnächst, Wochenplan

**Personenseite**:
Die rechte Spalte mit der ausgewählten Person, ihren Kontakten, Angehörigen und Stichtagen.
_Avoid_: Profil, Detailansicht, Steckbrief

**Kontakt eintragen**:
Die Handlung, einen Kontakt mit Art, Datum und Notiz zu einer Person zu speichern; erreichbar über den Kreis in der Liste und den Knopf auf der Personenseite.
_Avoid_: Log contact, Abhaken, Erledigen, Check-in

**Mehrere hinzufügen**:
Das Feld, in das der Nutzer mehrere Namen auf einmal einträgt, mit Tags und Schätzung für alle.
_Avoid_: Import, Bulk-Add, Massenanlage

**Diktat**:
Das Sprechen in ein Textfeld über das Mikrofon des Geräts; die Sprache ist eine Einstellung.
_Avoid_: Spracheingabe, Voice input, Transkription (für die Nutzerhandlung)

## Erinnern

**Tagesmeldung**:
Die eine Mitteilung pro Tag zur eingestellten Uhrzeit, nur wenn jemand fällig oder ein Stichtag nah ist; als Push im Browser oder als Hinweis in der App.
_Avoid_: Notification, Digest, Benachrichtigung (allein), Alarm

**Push**:
Der Weg der Tagesmeldung zum Browser, auch bei geschlossenem Fenster; braucht die Erlaubnis des Nutzers und auf dem Mac in Safari die App im Dock.
_Avoid_: Web Push, Notification (als Weg)

**Hinweis**:
Die Tagesmeldung als Streifen in der App, wenn Push nicht erlaubt oder nicht möglich ist; einmal am Tag, wegklickbar.
_Avoid_: Banner, Toast, Alert

**Kalender**:
Die Stichtage und Fälligkeiten eines Nutzers als abonnierbare Adresse und als Datei für die Kalender-App.
_Avoid_: iCal, Feed, Export (allein), ICS

**Kalenderadresse**:
Die geheime Adresse des Kalenders eines Nutzers; in den Einstellungen sichtbar und neu erzeugbar.
_Avoid_: Token, Link, URL, Secret

## Betrieb

**Datenordner**:
Der eine Ort für Datenbank, Push-Schlüssel und Sicherungen; `bindung ort` nennt ihn, `BINDUNG_DATEN` stellt ihn um.
_Avoid_: Data directory, Speicherort, Pfad

**Sicherung**:
Eine datierte JSON-Datei mit allem, was ein Nutzer eingetragen hat; `bindung sichern` schreibt sie, `bindung wiederherstellen` liest sie.
_Avoid_: Backup, Export, Dump
