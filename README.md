# Mahnwesen MVP

**Minimum Viable Product** zur automatisierten Verarbeitung von Rechnungsdaten
und zum Versand von Zahlungserinnerungen per E‑Mail.

Das Skript richtet sich an kleine und mittlere Unternehmen sowie
Finanzabteilungen, die einen einfachen, wartbaren Mahnprozess benötigen.

## Hauptfunktionen

- **API‑Synchronisation** – Kundendaten werden aus einer REST‑API abgerufen,
  validiert und in eine MySQL‑Datenbank übernommen.
- **Mahnungserstellung** – Für alle unbezahlten Rechnungen wird eine
  personalisierte PDF‑Mahnung generiert.
- **E‑Mail‑Versand** – Die PDF wird per SMTP (TLS) an die hinterlegte
  E‑Mail‑Adresse des Kunden gesendet.
- **Konfigurierbare Mahnstufen** – Die maximale Anzahl von Mahnungen pro Kunde
  wird über die Umgebungsvariable `REMINDER_LIMIT` gesteuert.
- **Protokollierung** – Kunden ohne E‑Mail‑Adresse werden erfasst, erhalten
  jedoch keine Benachrichtigung.

## Technologien

| Bereich               | Bibliothek / Werkzeug          |
|-----------------------|--------------------------------|
| Sprache               | Python 3.11                    |
| Datenbank‑ORM         | SQLAlchemy                     |
| PDF‑Erzeugung         | ReportLab                      |
| Konfiguration         | python‑dotenv                  |
| HTTP‑Client           | requests                       |
| E‑Mail‑Versand        | smtplib, email (Standard)      |
| Containerisierung     | Docker                         |
| Datenbank             | MySQL                          |

## Projektstruktur
├── main.py # Hauptskript
├── Dockerfile # Containerbauanleitung
├── requirements.txt # Python‑Abhängigkeiten
├── .env.example # Vorlage für Umgebungsvariablen (zum Kopieren nach .env)
├── .gitignore
└── README.md

## Voraussetzungen

- Python 3.11 oder höher (falls kein Docker verwendet wird)
- MySQL‑Server (Version 5.7+ empfohlen)
- SMTP‑Zugangsdaten (z. B. Gmail mit App‑Passwort)
- Optional: Docker Desktop

## Schnellstart (Docker)

```bash
docker build -t mahnwesen-mvp .
docker run --rm --env-file .env mahnwesen-mvp
```

## Schnellstart (lokale Python‑Umgebung)
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# .env anpassen und Daten eintragen
python main.py
```

## Testing & Qualitätssicherung
Um die Zuverlässigkeit des Mahnwesens zu gewährleisten, wurde das Projekt mit einer umfassenden Testsuite auf Basis von pytest ausgestattet.

**Test-Schwerpunkte** 

- Unit-Tests: Validierung der Datenbereinigung (clean_api_data) und der korrekten Typ-Konvertierung von API-Rückgabewerten.

- Dokumenten-Validierung: Prüfung der PDF-Generierung im Arbeitsspeicher (io.BytesIO), um sicherzustellen, dass gültige Dokumente ohne Dateisystem-Abhängigkeiten erzeugt werden.

- Business Logic & Mocking: Einsatz von pytest-mock, um die Datenbank-Session и den SMTP-Versand zu isolieren. Dies ermöglicht die Prüfung der Mahnlogik, ohne echte E-Mails zu versenden oder eine reale Datenbank zu benötigen.

- Negative Testing: Verifizierung, dass nur Kunden mit offenem Saldo (ist_bezahlt == False) verarbeitet werden, während bezahlte Konten ignoriert werden.

## Ausführung der Tests
Abhängigkeiten installieren:

```Bash
pip install pytest pytest-mock
```
Tests starten:

```Bash
pytest tests/test_main.py -v
```

## Hinweise zum MVP‑Status

Dieses Projekt ist bewusst als MVP umgesetzt. Es enthält grundlegende
Fehlerbehandlungen (try/except) und einfache print‑Ausgaben. Für einen
Produktiveinsatz sollten folgende Erweiterungen vorgenommen werden:

Ersatz von print durch das logging‑Modul
Spezifischere Ausnahmebehandlung je Fehlertyp
Datenbankmigrationen mit Alembic statt Base.metadata.create_all
Automatische Wiederholungsversuche bei Netzwerkfehlern
Unit‑ und Integrationstests

## Code-Architektur
Die Anwendung ist modular aufgebaut, um eine klare Trennung zwischen Datenverarbeitung, Dokumentenerzeugung und Kommunikation zu gewährleisten:

- clean_api_data: Ein Utility-Modul zur Datenbereinigung. Es normalisiert die Schlüssel des API-Antwort-Dictionaries (Entfernung von Leerzeichen), um Konsistenz mit dem Datenbank-Schema sicherzustellen.

- sync_with_api: Der Kernprozess der Datensynchronisation. Er nutzt SQLAlchemy-Transaktionen und die session.merge()-Methode, um Datensätze effizient zu aktualisieren oder neu anzulegen, ohne Duplikate zu erzeugen.

- generate_invoice_pdf: Verwendet die ReportLab-Bibliothek, um personalisierte Mahnungen im PDF-Format zu generieren. Die PDF-Daten werden direkt im Arbeitsspeicher (io.BytesIO) verarbeitet, was die Performance erhöht und Dateisystem-Abhängigkeiten minimiert.

- send_email_with_pdf: Ein Abstraktions-Layer für den SMTP-Versand. Er kapselt die Komplexität der MIME-Erstellung und der TLS-gesicherten Kommunikation mit dem Mail-Server.

- send_reminders: Die Business-Logik-Schicht. Hier wird entschieden, welche Kunden basierend auf dem ist_bezahlt-Status und dem REMINDER_LIMIT eine Mahnung erhalten. Nach erfolgreichem Versand wird der Mahnzähler persistent in der Datenbank erhöht.