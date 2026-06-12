from same.anonymize import anonymize


def test_redacts_phones_poc_and_dni():
    assert anonymize("NUMERO DE POC 1178562532") == "NUMERO DE POC [NUM]"
    assert anonymize("TELEF.- 1122712171") == "TELEF.- [NUM]"
    assert anonymize("POC 11-65561952 ALCALDIA") == "POC [NUM] ALCALDIA"
    assert anonymize("DNI 30123456") == "DNI [NUM]"
    # teléfono partido por un espacio (formato real del PDF)
    assert anonymize("NRO DE POC 11-2829- 4057____") == "NRO DE POC [NUM]____"
    assert anonymize("POC COMISARIA: 15-4071- 7749") == "POC COMISARIA: [NUM]"


def test_redacts_police_badge_numbers():
    assert anonymize("OFICIAL OJEDA LP 15798") == "OFICIAL OJEDA [LP]"
    assert anonymize("OF MAYOR L.P. 4925 ALCALDIA 10") == "OF MAYOR [LP] ALCALDIA 10"
    assert anonymize("AGENTE LEGAJO 1234") == "AGENTE [LP]"
    # no se confunde con códigos de dependencia ni con [LP] ya redactado
    assert anonymize("COMISARIA 4D - CALIFORNIA 1850") == "COMISARIA 4D - CALIFORNIA 1850"
    assert anonymize("OF [NOMBRE] [LP] SOLICITA") == "OF [NOMBRE] [LP] SOLICITA"


def test_removes_id_remoto_block():
    out = anonymize("AUTOLESIONADO [Id.Remoto: 48132107]")
    assert "Id.Remoto" not in out
    assert "48132107" not in out
    assert out == "AUTOLESIONADO"


def test_removes_truncated_id_remoto_without_closing_bracket():
    # bloque truncado al borde de celda (sin `]`)
    out = anonymize("INCENDIO ES TODO [Id.Remoto: 48132107")
    assert "Id.Remoto" not in out
    assert "48132107" not in out
    assert out == "INCENDIO ES TODO"


def test_preserves_short_codes_and_vitals():
    # códigos de dependencia / direcciones (1-4 díg.) se conservan
    assert anonymize("COMISARIA 4D - CALIFORNIA 1850") == "COMISARIA 4D - CALIFORNIA 1850"
    assert anonymize("ALCAIDIA 9 GANA 430") == "ALCAIDIA 9 GANA 430"
    # signos vitales se conservan
    assert anonymize("TA 120/80 TEMP 36.5") == "TA 120/80 TEMP 36.5"


def test_none_and_empty_pass_through():
    assert anonymize(None) is None
    assert anonymize("") == ""
