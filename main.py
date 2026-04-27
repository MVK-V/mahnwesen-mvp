"""
MVP zur automatisierten Verarbeitung von Rechnungsdaten und Mahnungsversand.

Das Skript synchronisiert Kundendaten aus einer REST-API, validiert und
persistiert sie in einer MySQL-Datenbank. Anschließend werden unbezahlte
Rechnungen unterhalb der konfigurierten Mahnstufe ermittelt, eine
personalisierte PDF-Mahnung generiert und diese per E-Mail versendet.
Der Zähler `reminders_count` wird nach erfolgreichem Versand erhöht, um
die Anzahl der Mahnungen je Kunde zu begrenzen.

Verwendete Technologien: SQLAlchemy, ReportLab, python-dotenv, requests, smtplib.

Externe Abhängigkeit: REST-Endpunkt https://retoolapi.dev/BnzcNn/data
"""

import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email import encoders
import io
from datetime import datetime

from sqlalchemy import create_engine, Column, Integer, String, Boolean
from sqlalchemy.orm import declarative_base, sessionmaker
from dotenv import load_dotenv
import requests
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm

#KONFIGURATION
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
EMAIL_FROM = os.getenv("EMAIL_FROM")
REMINDER_LIMIT = int(os.getenv("REMINDER_LIMIT", 3))

if not all([DATABASE_URL, SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, EMAIL_FROM]):
    raise ValueError("Nicht alle erforderlichen Umgebungsvariablen sind in .env definiert.")

#DATENBANK
engine = create_engine(DATABASE_URL)
Base = declarative_base()
SessionLocal = sessionmaker(bind=engine)


class Client(Base):
    __tablename__ = 'clients'
    id = Column(Integer, primary_key=True)
    name = Column(String(255))
    konto = Column(Integer)
    summe = Column(Integer)
    adresse = Column(String(500))
    ist_bezahlt = Column(Boolean, default=False)
    email = Column(String(255))
    reminders_count = Column(Integer, default=0)


Base.metadata.create_all(engine)


#HILFSFUNKTIONEN
def clean_api_data(raw_data: dict) -> dict:
    """
    Entfernt führende/nachfolgende Leerzeichen aus allen Schlüsseln des API-Wörterbuchs.
    """

    return {key.strip(): value for key, value in raw_data.items()}


def generate_invoice_pdf(client: Client) -> bytes:
    """
    Erzeugt eine personalisierte PDF-Mahnung für einen Kunden.

    Die PDF wird im Speicher über `BytesIO` generiert und direkt als Byte-String
    zurückgegeben – geeignet für den Versand als E-Mail-Anhang.
    """

    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    c.setFont("Helvetica-Bold", 16)
    c.drawString(20 * mm, height - 20 * mm, "MAHNUNG")

    c.setFont("Helvetica", 12)
    y = height - 40 * mm
    c.drawString(20 * mm, y, f"Name: {client.name}")
    y -= 7 * mm
    c.drawString(20 * mm, y, f"Die Adresse: {client.adresse or 'fehlt'}")
    y -= 7 * mm
    c.drawString(20 * mm, y, f"Die Nummer des Kontos: {client.konto}")
    y -= 7 * mm
    c.drawString(20 * mm, y, f"Die Summe : {client.summe} €")
    y -= 10 * mm

    text_lines = [
        f"Sehr geehrte/r {client.name},",
        "",
        "wir erlauben uns, Sie darauf hinzuweisen, dass für das oben genannte Konto",
        f"noch ein Betrag in Höhe von {client.summe} € zur Zahlung aussteht.",
        "Wir bitten um Begleichung innerhalb der nächsten 10 Tage.",
        "",
        "Mit freundlichen Grüßen,",
        "XXX GmbH"
    ]
    for line in text_lines:
        c.drawString(20 * mm, y, line)
        y -= 6 * mm

    c.setFont("Helvetica-Oblique", 10)
    c.drawString(20 * mm, 30 * mm, f"Erstellt am: {datetime.now().strftime('%d.%m.%Y %H:%M')}")

    c.save()
    buffer.seek(0)
    return buffer.read()


def send_email_with_pdf(to_email: str, subject: str, body: str,
                        pdf_bytes: bytes, filename: str):
    """
    Versendet eine E-Mail mit PDF-Anhang über einen konfigurierten SMTP-Server.

    Baut ein MIME-Multipart-Objekt aus Textkörper und Base64-kodiertem PDF-Anhang auf,
    stellt eine TLS-gesicherte Verbindung zum SMTP-Server her, authentifiziert sich
    mit den in der Umgebung hinterlegten Zugangsdaten und versendet die Nachricht.
    """
    msg = MIMEMultipart()
    msg['From'] = EMAIL_FROM
    msg['To'] = to_email
    msg['Subject'] = subject

    msg.attach(MIMEText(body, 'plain'))

    part = MIMEBase('application', 'octet-stream')
    part.set_payload(pdf_bytes)
    encoders.encode_base64(part)
    part.add_header('Content-Disposition', f'attachment; filename="{filename}"')
    msg.attach(part)

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.starttls()
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.send_message(msg)


#API-SYNCHRONISATION
def sync_with_api():
    """
    Synchronisiert die Kundendaten aus dem externen API-Endpunkt mit der Datenbank.

 Ruft die Daten per GET-Request ab, bereinigt die Schlüssel, validiert und konvertiert
    die Felder (insb. `summe` und `ist_bezahlt`) und aktualisiert bzw. erstellt die
    Datensätze über `session.merge()` in einer Transaktion. Bei Fehlern wird die
    Ausführung abgebrochen und der Fehler protokolliert.
    """
    url = "https://retoolapi.dev/BnzcNn/data"
    try:
        response = requests.get(url)
        response.raise_for_status()
        all_data = response.json()
        if not all_data:
            print("API hat eine leere Liste zurückgegeben.")
            return
    except Exception as e:  #nur für MVP gemeinsame Fehlerbearbeitung
        print(f"Fehler beim Abrufen der API: {e}")
        return

    with SessionLocal() as session:
        for item in all_data:
            data = clean_api_data(item)

            raw_summe = data.get("summe", 0)
            try:
                clean_summe = int(raw_summe)
            except (ValueError, TypeError):
                clean_summe = 0
                print(f"Warnung: Ungültiger Betrag '{raw_summe}' für ID {data.get('id')}")

            ist_bezahlt_raw = data.get("ist_bezahlt", False)
            if isinstance(ist_bezahlt_raw, str):
                ist_bezahlt = ist_bezahlt_raw.lower() in ('true', '1', 'yes')
            else:
                ist_bezahlt = bool(ist_bezahlt_raw)

            client = Client(
                id=data.get("id"),
                name=data.get("name"),
                konto=data.get("konto"),
                summe=clean_summe,
                adresse=data.get("adresse"),
                ist_bezahlt=ist_bezahlt,
                email=data.get("email_adresse")
            )
            session.merge(client)

        session.commit()


#MAHNUNGSVERSAND
def send_reminders():
    """
    Ermittelt alle offenen Posten mit verbleibenden Mahnstufen gemäß

    `REMINDER_LIMIT`, generiert die zugehörigen PDF-Mahnungen und wickelt
    den E-Mail-Versand ab. Nach erfolgreicher Zustellung wird die
    Erinnerungsfrequenz (`reminders_count`) persistent erhöht. Kunden ohne
    hinterlegte E-Mail-Adresse werden gesondert protokolliert; im
    Fehlerfall wird die Transaktion isoliert zurückgerollt.
    """
    with SessionLocal() as session:
        unpaid_clients = session.query(Client).filter(
            Client.ist_bezahlt == False,
            Client.reminders_count < REMINDER_LIMIT
        ).all()

        clients_without_email = [c for c in unpaid_clients if not c.email]
        clients_to_remind = [c for c in unpaid_clients if c.email]

        if clients_without_email:
            for c in clients_without_email:
                print(f"ID {c.id}, {c.name}, Das Konto {c.konto}, Die Summe {c.summe}")

        if not clients_to_remind:
            print("Alle haben rechtzeitig überwiesen.")
            return

        for client in clients_to_remind:
            try:
                pdf_bytes = generate_invoice_pdf(client)
                filename = f"invoice_{client.konto}_{datetime.now().strftime('%Y%m%d')}.pdf"

                subject = "Mahnung"
                body = (
                    f"Sehr geehrte/r {client.name},\n\n"
                    f"im Anhang erhalten Sie eine Übersicht zum offenen Konto Nr. {client.konto} "
                    f"mit einem ausstehenden Betrag in Höhe von {client.summe} €.\n"
                    "Wir bitten um zeitnahe Überweisung.\n\n"
                    "Mit freundlichen Grüßen,\nFinanzabteilung"
                )

                send_email_with_pdf(client.email, subject, body, pdf_bytes, filename)

                client.reminders_count += 1
                session.commit()

                print(f"Eine Mahnung wurde für ID {client.id} ({client.email}) geschickt, "
                      f"Der Versuch {client.reminders_count}")

            except Exception as e:  #nur für MVP gemeinsame Fehlerbearbeitung
                session.rollback()
                print(f"Der Fehler beim Versand für ID {client.id}: {e}")


#EINSTIEGSPUNKT
def main():
    """
    Tägliche Ausführungsroutine: Gleicht die lokale Datenbank mit der API ab und
    initiiert den Versand fälliger Mahnungen.
    """
    sync_with_api()
    send_reminders()


if __name__ == "__main__":
    main()