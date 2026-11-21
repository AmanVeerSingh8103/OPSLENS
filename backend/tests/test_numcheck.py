from opslens.numcheck import collect_numbers, find_unsupported

EV = collect_numbers({"revenue": 1234567.89, "growth_pct": -12.34, "n": 41, "peak": "2011-11"})


def test_supported_forms():
    for t in ["Revenue was £1.23m", "Revenue of £1,234,568", "down 12.3%", "fell 12%", "41 invoices", "peaked in 2011-11 (2011)"]:
        assert find_unsupported(t, EV) == [], t


def test_unsupported_numbers_caught():
    assert find_unsupported("Revenue grew 45%", EV) == ["45%"]
    assert find_unsupported("Revenue was £2.5m", EV)
    assert find_unsupported("About 9,999 invoices", EV)


def test_evidence_ids_and_small_counts_ignored():
    assert find_unsupported("See E12 and the top 5 products across 3 tools", EV) == []
