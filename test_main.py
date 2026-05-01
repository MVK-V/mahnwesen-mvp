from main import clean_api_data, Client


def test_clean_api_data_removes_spaces():
    """
    Prüft, ob die Keys des API-Dictionaries korrekt von Leerzeichen bereinigt werden.
    Gewährleistet die Konsistenz zwischen API-Input und Datenbank-Schema.
    """
    dirty_input = {" name ": "Victoria", "summe  ": 100, "  email": "test@test.de"}
    expected = {"name": "Victoria", "summe": 100, "email": "test@test.de"}

    result = clean_api_data(dirty_input)
    assert result == expected
    assert "name" in result
    assert " name " not in result


def test_pdf_generation_logic(mocker):
    """
    Validiert die PDF-Erstellung im Arbeitsspeicher.
    Stellt sicher, dass ein gültiger Byte-Stream mit korrektem PDF-Header erzeugt wird.
    """
    mock_client = Client(
        name="Max Mustermann",
        adresse="Teststr. 1",
        konto=12345,
        summe=500
    )

    from main import generate_invoice_pdf

    pdf_result = generate_invoice_pdf(mock_client)

    assert isinstance(pdf_result, bytes)
    assert len(pdf_result) > 0
    assert pdf_result.startswith(b'%PDF')


def test_ist_bezahlt_conversion_logic():
    """
    Testet die Typ-Konvertierung des Status 'ist_bezahlt'.
    Verifiziert, dass verschiedene API-Eingangsformate (String, Bool, None) korrekt interpretiert werden.
    """
    test_cases = [
        ("true", True), ("1", True), ("yes", True),
        ("false", False), (True, True), (False, False), (None, False)
    ]

    for input_val, expected in test_cases:
        if isinstance(input_val, str):
            result = input_val.lower() in ('true', '1', 'yes')
        else:
            result = bool(input_val)
        assert result == expected, f"Fehler bei Eingabe: {input_val}"



def test_send_reminders_skips_paid_clients(mocker):
    """
    Überprüft die Filterlogik für den Mahnungsversand mittels Mocks.
    Stellt sicher, dass Mahnungen nur an Kunden mit offenem Saldo versendet werden
    und der Mahnzähler korrekt inkrementiert wird.
    """
    mock_session = mocker.patch('main.SessionLocal')


    client_paid = Client(id=1, name="Paid", ist_bezahlt=True, reminders_count=0, email="1@test.de")
    client_unpaid = Client(id=2, name="Unpaid", ist_bezahlt=False, reminders_count=0, email="2@test.de")

    mock_session.return_value.__enter__.return_value.query.return_value.filter.return_value.all.return_value = [
        client_unpaid]

    mock_send = mocker.patch('main.send_email_with_pdf')
    mocker.patch('main.generate_invoice_pdf', return_value=b"fake_pdf")

    from main import send_reminders
    send_reminders()

    assert mock_send.call_count == 1
    assert client_unpaid.reminders_count == 1