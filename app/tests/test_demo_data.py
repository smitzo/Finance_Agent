from app.services.demo_data_service import (
    DEMO_BILL_COUNT,
    DEMO_DETERMINISTIC_COUNT,
    DEMO_LLM_COUNT,
    build_demo_dataset,
)


def test_demo_dataset_shape():
    data = build_demo_dataset()

    assert len(data["freight_bills"]) == DEMO_BILL_COUNT
    assert len(data["shipments"]) == DEMO_BILL_COUNT
    assert len(data["bills_of_lading"]) == DEMO_BILL_COUNT
    assert len(data["carrier_contracts"]) >= DEMO_BILL_COUNT


def test_demo_dataset_has_deterministic_and_llm_paths():
    bills = build_demo_dataset()["freight_bills"]

    deterministic = [bill for bill in bills if bill["carrier_id"]]
    llm = [bill for bill in bills if not bill["carrier_id"]]

    assert len(deterministic) == DEMO_DETERMINISTIC_COUNT
    assert len(llm) == DEMO_LLM_COUNT
    assert all(bill["shipment_reference"] for bill in bills)
