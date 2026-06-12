from same.extract import _clean, _is_noise_row, _parse_si_no


def test_clean_collapses_whitespace_and_newlines():
    assert _clean("  04 -\nTRAUMATISMO   LEVE ") == "04 - TRAUMATISMO LEVE"
    assert _clean("") is None
    assert _clean(None) is None


def test_parse_si_no():
    assert _parse_si_no("Si") is True
    assert _parse_si_no("No") is False
    assert _parse_si_no("") is None
    assert _parse_si_no(None) is None


def test_is_noise_row_detects_title_and_header():
    title = ["Intervenciones del SAME realizadas ...", None, None, None]
    header = ["Fecha y Hora", "Dirección", "Altura", "Motivo de Intervención"]
    data = ["11/5/2026 17:45", "ARTILLEROS", "2081", "..."]
    assert _is_noise_row(title) is True
    assert _is_noise_row(header) is True
    assert _is_noise_row(data) is False
