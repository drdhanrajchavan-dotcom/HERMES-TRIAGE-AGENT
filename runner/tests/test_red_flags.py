from clinic_agency.safety.red_flags import classify_red_flags


def test_red_flag_requires_escalation_for_swelling_with_fever() -> None:
    result = classify_red_flags("My face is swollen and hot and I have a fever")

    assert result.must_escalate is True
    assert "fever" in result.matched_terms
    assert "swollen" in result.matched_terms


def test_red_flag_does_not_escalate_routine_pricing_question() -> None:
    result = classify_red_flags("How much does laser hair removal cost?")

    assert result.must_escalate is False
    assert result.matched_terms == ()
