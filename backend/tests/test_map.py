"""Dependency map accuracy against the hand-checked answer key (needs the pinned Bank of Anthos clone)."""
import pytest

from app.mapbuild.project import load_project

project = load_project()
pytestmark = pytest.mark.skipif(not project.root.exists(), reason="run scripts/fetch_repo.ps1 first")


@pytest.fixture(scope="module")
def built():
    from app.mapbuild.build import build_map
    return build_map(project)


@pytest.fixture(scope="module")
def accuracy(built):
    from app.mapbuild.mapcheck import check_map
    return check_map(built[0])


def test_inventory_finds_all_services_and_databases(accuracy):
    for key in ("services", "databases", "tables", "endpoints"):
        assert accuracy[key]["recall"] == 1.0 and accuracy[key]["precision"] == 1.0, accuracy[key]


def test_data_access_and_token_trust_are_exact(accuracy):
    for key in ("data_access", "token_trust"):
        assert accuracy[key]["recall"] == 1.0 and accuracy[key]["precision"] == 1.0, accuracy[key]


def test_api_calls_have_no_false_links_and_only_the_ambiguous_one_missing(built, accuracy):
    api = accuracy["api_calls"]
    assert api["precision"] == 1.0
    assert api["missing"] in ([], [("frontend", "ep:contacts:GET /contacts/{username}")])
    ambiguous = [u for u in built[1]["unresolved"] if u["kind"] == "ambiguous_method"]
    if api["missing"]:
        assert ambiguous and set(ambiguous[0]["candidates"]) == {"ep:contacts:GET /contacts/{username}",
                                                                   "ep:contacts:POST /contacts/{username}"}


def test_every_edge_has_proof(built):
    pm = built[0]
    for e in pm.edges.values():
        assert e.evidence, f"edge without evidence: {e.id}"


def test_ledgerwriter_checks_balance_via_config_wiring(built):
    pm = built[0]
    e = pm.edges["svc:ledgerwriter|calls_api|ep:balancereader:GET /balances/{accountId}"]
    assert e.confidence == 1.0 and "BALANCES_API_ADDR" in e.props["how"]
