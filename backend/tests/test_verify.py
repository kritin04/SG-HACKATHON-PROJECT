from app.llm.verify import verify_claims, verify_doc_fix

PACK = {"E-aaaaaa": "def compute_transfer_fee(amount, currency, channel='BRANCH'):\n    rate = 1",
        "E-bbbbbb": "Regulatory Reporting Hub receives the daily extract"}


def test_forged_evidence_id_is_rejected():
    out = verify_claims([{"text": "x", "evidence_ids": ["E-ffffff"], "quote": "daily extract"}], PACK)
    assert out[0]["verified"] is False and out[0]["evidence_ids"] == []


def test_non_verbatim_quote_is_rejected():
    out = verify_claims([{"text": "x", "evidence_ids": ["E-bbbbbb"], "quote": "sends a weekly extract"}], PACK)
    assert out[0]["verified"] is False


def test_verbatim_quote_is_accepted():
    out = verify_claims([{"text": "x", "evidence_ids": ["E-bbbbbb"], "quote": "receives the daily extract"}], PACK)
    assert out[0]["verified"] is True


def test_unknown_test_target_is_flagged():
    out = verify_claims([{"title": "t", "target": "made_up_function", "evidence_ids": ["E-aaaaaa"]}], PACK,
                        known_names={"payments_service.fees.compute_transfer_fee"})
    assert out[0]["verified"] is False


def test_doc_fix_that_changes_heading_or_keeps_stale_token_is_rejected():
    orig = "## Fees\n\nUses `calculate_fee(a)`."
    assert verify_doc_fix(orig, "## Pricing\n\nUses `compute_transfer_fee(a)`.", ["`calculate_fee("], ["compute_transfer_fee"])
    assert verify_doc_fix(orig, "## Fees\n\nUses `calculate_fee(a)`.", ["`calculate_fee("], ["compute_transfer_fee"])
    assert verify_doc_fix(orig, "## Fees\n\nUses `compute_transfer_fee(a)`.\n\n## Extra\n\nx", [], []) 
    assert verify_doc_fix(orig, "## Fees\n\nUses `compute_transfer_fee(a)`.", ["`calculate_fee("], ["compute_transfer_fee"]) == []


def test_wrong_citation_is_corrected_only_when_quote_is_verbatim_elsewhere():
    out = verify_claims([{"text": "x", "evidence_ids": ["E-aaaaaa"], "quote": "receives the daily extract"}], PACK)
    assert out[0]["verified"] and "E-bbbbbb" in out[0]["evidence_ids"] and out[0]["citation_corrected"]


def test_inline_citations_are_stripped():
    from app.llm.verify import strip_inline_citations
    s = "Docs are missing. This must be fixed, as per the evidence in [E-0ceba5], [E-c50102], and [E-f4d266]."
    assert strip_inline_citations(s) == "Docs are missing. This must be fixed."
