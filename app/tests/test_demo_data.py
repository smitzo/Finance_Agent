from app.services.demo_data_service import (
    DEMO_BILL_COUNT,
    DEMO_ANOMALY_COUNT,
    DEMO_DETERMINISTIC_COUNT,
    DEMO_EDGE_SCENARIOS,
    DEMO_LLM_COUNT,
    DEMO_SCENARIO_EXPECTATIONS,
    build_demo_dataset,
)


def test_demo_dataset_shape():
    data = build_demo_dataset()

    assert len(data["freight_bills"]) == DEMO_BILL_COUNT
    # Missing-evidence and multi-BOL scenarios intentionally make these counts
    # differ from the bill count.
    assert len(data["shipments"]) == DEMO_BILL_COUNT - 1
    assert len(data["bills_of_lading"]) == DEMO_BILL_COUNT - 1
    assert len(data["carrier_contracts"]) >= DEMO_BILL_COUNT - 2
    assert len(data["companies"]) == 1
    assert len(data["partner_firms"]) == 1


def test_demo_dataset_has_deterministic_and_llm_paths():
    bills = build_demo_dataset()["freight_bills"]

    deterministic = [bill for bill in bills if bill["demo_category"] == "deterministic"]
    llm = [bill for bill in bills if bill["demo_category"] == "llm"]
    anomalies = [bill for bill in bills if bill["demo_category"] == "edge"]

    assert len(deterministic) == DEMO_DETERMINISTIC_COUNT
    assert len(llm) == DEMO_LLM_COUNT
    assert len(anomalies) == DEMO_ANOMALY_COUNT
    assert sum(bill["demo_kind"] == "contract_ambiguity" for bill in llm) == DEMO_LLM_COUNT // 2
    assert sum(bill["demo_kind"] == "fuzzy_carrier_and_contract" for bill in llm) == DEMO_LLM_COUNT // 2


def test_demo_edge_portfolio_covers_documented_scenarios():
    bills = build_demo_dataset()["freight_bills"]
    edge_bills = [bill for bill in bills if bill["demo_category"] == "edge"]

    assert [bill["demo_kind"] for bill in edge_bills] == list(DEMO_EDGE_SCENARIOS)
    assert all(bill["demo_expectation"] for bill in edge_bills)
    assert set(DEMO_EDGE_SCENARIOS) == set(DEMO_SCENARIO_EXPECTATIONS)

    duplicate_bills = [bill for bill in edge_bills if bill["demo_kind"] == "duplicate_number"]
    assert len(duplicate_bills) == 2
    assert len({bill["bill_number"] for bill in duplicate_bills}) == 1
    assert sum(bill["carrier_id"] is None for bill in duplicate_bills) == 1

    deterministic = [bill for bill in bills if bill["demo_category"] == "deterministic"]
    assert len({bill["lane"] for bill in deterministic}) == DEMO_DETERMINISTIC_COUNT

    assert any(bill["shipment_reference"] is None for bill in edge_bills)
    assert any(bill["demo_kind"] == "unknown_carrier" for bill in edge_bills)


def test_demo_primary_keys_are_stable_and_disjoint_between_tenants():
    first = build_demo_dataset("demo")
    first_again = build_demo_dataset("demo")
    second = build_demo_dataset("another-tenant")

    for collection in (
        "partner_firms",
        "companies",
        "carriers",
        "carrier_contracts",
        "shipments",
        "bills_of_lading",
        "freight_bills",
    ):
        first_ids = {row["id"] for row in first[collection]}
        assert first_ids == {row["id"] for row in first_again[collection]}
        assert first_ids.isdisjoint({row["id"] for row in second[collection]})
