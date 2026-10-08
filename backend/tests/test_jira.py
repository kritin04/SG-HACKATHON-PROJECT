"""Jira connector: rich text (ADF) parsing and acceptance-criteria extraction."""
from app.jira.adf import adf_to_text, text_to_adf
from app.jira.parse import parse_issue


def test_adf_round_trip_keeps_paragraphs_and_bullets():
    doc = text_to_adf("First paragraph.\n\nSecond one.", ["Rule A", "Rule B"], "Acceptance criteria")
    text = adf_to_text(doc)
    assert "First paragraph." in text and "Second one." in text
    assert "- Rule A" in text and "- Rule B" in text


def test_parse_issue_splits_acceptance_criteria_from_description():
    raw = {"key": "BOA-1", "fields": {
        "summary": "Phone at sign-up", "issuetype": {"name": "Story"}, "status": {"name": "To Do"},
        "priority": {"name": "High"}, "labels": ["personal-data"], "components": [{"name": "Accounts"}],
        "assignee": {"displayName": "Mei Tan"}, "reporter": None,
        "description": text_to_adf("We need a phone number.", ["Field is required", "Saved with profile"], "Acceptance criteria")}}
    p = parse_issue(raw, None, "https://example.atlassian.net")
    f = p["fields"]
    assert f["description"] == "We need a phone number."
    assert f["acceptance_criteria"] == ["Field is required", "Saved with profile"]
    assert p["url"] == "https://example.atlassian.net/browse/BOA-1"
    assert f["assignee"]["displayName"] == "Mei Tan" and f["components"] == [{"name": "Accounts"}]


def test_plain_text_description_from_jira_server_is_accepted():
    p = parse_issue({"key": "X-1", "fields": {"summary": "s", "description": "Plain text\nAcceptance criteria:\n* one\n* two"}})
    assert p["fields"]["acceptance_criteria"] == ["one", "two"]
