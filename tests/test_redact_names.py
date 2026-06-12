from same.redact_names import _clean_output, _hash, missing_texts


def test_missing_texts_uses_hash_cache():
    distinct = ["OFICIAL OJEDA", "DOLOR DE CABEZA"]
    cache = {_hash("OFICIAL OJEDA"): "OFICIAL [NOMBRE]"}
    # solo el que no está cacheado (por hash) queda pendiente
    assert missing_texts(distinct, cache) == ["DOLOR DE CABEZA"]
    assert missing_texts(distinct, {}) == distinct


def test_clean_output_strips_wrapping_quotes_and_space():
    assert _clean_output('  "TEXTO ANON"  ') == "TEXTO ANON"
    assert _clean_output("TEXTO SIN COMILLAS") == "TEXTO SIN COMILLAS"
    assert _clean_output("'OTRO'") == "OTRO"


def test_hash_is_stable_and_distinct():
    assert _hash("abc") == _hash("abc")
    assert _hash("abc") != _hash("abd")
