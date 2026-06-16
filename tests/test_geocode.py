from same.geocode import _in_caba, geocode


def test_in_caba_bounds():
    assert _in_caba(-34.6472, -58.3748)  # CALIFORNIA 1850 (CABA)
    assert not _in_caba(-34.7912, -58.5229)  # AV JUAN B JUSTO 430 mal-geocodificado (GBA)
    assert not _in_caba(-34.5077, -58.5064)  # CAP JUSTO G BERMUDEZ (norte, fuera)


def test_geocode_skips_altura_zero_and_empty():
    cache = {}
    assert geocode("DELFO CABRERA", 0, cache) is None
    assert geocode("", 1850, cache) is None
    assert cache == {}  # no consulta ni cachea


def test_geocode_rejects_out_of_caba_cached():
    cache = {"AV JUAN B JUSTO|430": [-34.7912, -58.5229]}
    assert geocode("AV JUAN B JUSTO", 430, cache) is None  # bounds reject sobre la caché
    cache = {"CALIFORNIA|1850": [-34.6472, -58.3748]}
    assert geocode("CALIFORNIA", 1850, cache) == [-34.6472, -58.3748]
