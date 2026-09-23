from acqlab.generator.documents import Doc, heading, money, pct, slot, table


def test_slot_fills_placeholders_from_template_or_llm_text():
    s = slot("x", "brief", "Debt of {{amount}} at {{rate}}.", amount=money(12.345), rate=pct(0.085))
    assert s.render() == "Debt of $12.3M at 8.5%."
    assert s.model_copy(update={"text": "At {{rate}}, debt is {{amount}}."}).render() == "At 8.5%, debt is $12.3M."


def test_pages_count_words_and_are_at_least_one():
    assert Doc(id="a", title="A", domain="filler", blocks=["word " * 130]).pages == 2
    assert Doc(id="b", title="B", domain="filler", blocks=["short"]).pages == 1


def test_styles_format_headings_and_tables_differently():
    assert heading("A", 2, "Notes") == "## Notes" and heading("B", 2, "Notes") == "SECTION 2. NOTES"
    assert table("A", ["k", "v"], [["x", "1"]]).startswith("| k | v |")
    assert table("B", ["k", "v"], [["x", "1"]]).endswith("x ........ 1")
