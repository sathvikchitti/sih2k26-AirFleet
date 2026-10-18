"""Fresh-state checks for pending transfer approval and physical receipt."""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.repositories import (
    InventoryRepository,
    TransferRepository,
    WorkOrderRepository,
    reset,
    snapshot,
)
from app.repositories.store import store
from app.services import maintenance_service, transfer_service


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("DEMO_PERMISSION_MODE", "hardened")
    monkeypatch.setenv("DEMO_RESET_ENABLED", "false")
    monkeypatch.setenv("ML_PROVIDER", "mock")
    monkeypatch.delenv("DEMO_SCENARIO", raising=False)
    reset()
    with TestClient(app) as instance:
        yield instance
    reset()


def _set_bravo_hp204(*, quantity=6, reserved=0, minimum=0, condition=90):
    inv = InventoryRepository.find("bravo", "HP-204")
    return InventoryRepository.update(
        inv["id"], quantity=quantity, reserved=reserved,
        minimum_reserve=minimum, condition_pct=condition,
    )


def _pending(*, part="HP-204", source="bravo", dest="alpha", quantity=1,
             work_order_id=None, for_aircraft=None):
    return transfer_service.create_transfer(
        part, source, dest, quantity=quantity,
        work_order_id=work_order_id, for_aircraft=for_aircraft,
    )


def test_approval_snapshots_current_validated_source_condition_and_receipt_uses_dispatch_value():
    reset()
    source = _set_bravo_hp204(condition=90)
    transfer = _pending(quantity=1)

    # The condition changes while the request is pending, but remains above
    # HP-204's current catalog minimum.
    InventoryRepository.update(source["id"], condition_pct=50)
    approved = transfer_service.approve_transfer(transfer["id"])
    assert approved["status"] == "IN_TRANSIT"
    assert approved["condition_pct"] == 50

    # Once dispatched, later changes to the source line do not change the
    # physical shipment's recorded condition.
    InventoryRepository.update(source["id"], condition_pct=35)
    received = transfer_service.receive_transfer(transfer["id"])
    destination = InventoryRepository.find("alpha", "HP-204")
    assert received["status"] == "RECEIVED"
    assert received["condition_pct"] == 50
    assert destination["condition_pct"] == 50


@pytest.mark.parametrize("change", ["quantity", "reservation", "reserve_floor", "condition"])
def test_approval_rechecks_changed_source_constraints_atomically(change):
    reset()
    _set_bravo_hp204(quantity=6, reserved=0, minimum=0, condition=90)
    transfer = _pending(quantity=4)
    inv = InventoryRepository.find("bravo", "HP-204")
    if change == "quantity":
        InventoryRepository.update(inv["id"], quantity=3)
    elif change == "reservation":
        InventoryRepository.update(inv["id"], reserved=3)
    elif change == "reserve_floor":
        InventoryRepository.update(inv["id"], minimum_reserve=3)
    else:
        InventoryRepository.update(inv["id"], condition_pct=30)
    before_approval = snapshot()

    with pytest.raises(transfer_service.TransferError):
        transfer_service.approve_transfer(transfer["id"])

    assert snapshot() == before_approval


@pytest.mark.parametrize(
    ("field", "value"),
    [("source_base", "unknown"), ("dest_base", "unknown"),
     ("dest_base", "bravo"), ("part_number", "UNKNOWN"), ("quantity", 0)],
)
def test_approval_rejects_malformed_transfer_identity_before_debit(field, value):
    reset()
    _set_bravo_hp204(quantity=6, condition=90)
    transfer = _pending(quantity=1)
    TransferRepository.update(transfer["id"], **{field: value})
    before_approval = snapshot()

    with pytest.raises(transfer_service.TransferError):
        transfer_service.approve_transfer(transfer["id"])

    assert snapshot() == before_approval


@pytest.mark.parametrize("new_status", ["IN_PROGRESS", "COMPLETED", "CANCELLED"])
def test_approval_rejects_work_order_that_becomes_unusable_while_pending(new_status):
    reset()
    work_order = maintenance_service.create_manual_work_order("A19", "AV-077")
    transfer = _pending(
        part="AV-077", source="charlie", dest="alpha", quantity=1,
        work_order_id=work_order["id"], for_aircraft="A19",
    )
    WorkOrderRepository.update(work_order["id"], status=new_status,
                               resource_reserved=new_status == "IN_PROGRESS")
    before_approval = snapshot()

    with pytest.raises(transfer_service.TransferError):
        transfer_service.approve_transfer(transfer["id"])

    assert snapshot() == before_approval


@pytest.mark.parametrize("changed_link", ["work_order_missing", "component", "destination", "aircraft"])
def test_approval_revalidates_linked_work_order_relationships_atomically(changed_link):
    reset()
    work_order = maintenance_service.create_manual_work_order("A19", "AV-077")
    transfer = _pending(
        part="AV-077", source="charlie", dest="alpha", quantity=1,
        work_order_id=work_order["id"], for_aircraft="A19",
    )
    if changed_link == "work_order_missing":
        store()["work_orders"].remove(work_order)
    elif changed_link == "component":
        WorkOrderRepository.update(work_order["id"], required_component="FP-102")
    elif changed_link == "destination":
        WorkOrderRepository.update(work_order["id"], base_id="bravo")
    else:
        WorkOrderRepository.update(work_order["id"], aircraft_id="A17")
    before_approval = snapshot()

    with pytest.raises(transfer_service.TransferError):
        transfer_service.approve_transfer(transfer["id"])

    assert snapshot() == before_approval


def test_create_rejects_terminal_or_in_progress_work_order_without_side_effects():
    reset()
    work_order = maintenance_service.create_manual_work_order("A19", "AV-077")
    maintenance_service.start_maintenance(work_order["id"])
    maintenance_service.complete_maintenance(work_order["id"])
    before = snapshot()

    with pytest.raises(transfer_service.TransferError):
        _pending(part="AV-077", source="charlie", dest="alpha",
                 work_order_id=work_order["id"], for_aircraft="A19")

    assert snapshot() == before


def test_scheduled_waiting_work_order_remains_eligible_for_resource_transfer():
    reset()
    work_order = maintenance_service.create_manual_work_order("A17", "HP-204")
    WorkOrderRepository.update(work_order["id"], status="SCHEDULED")
    transfer = _pending(
        part="HP-204", source="bravo", dest="alpha", quantity=1,
        work_order_id=work_order["id"], for_aircraft="A17",
    )

    approved = transfer_service.approve_transfer(transfer["id"])
    assert approved["status"] == "IN_TRANSIT"


def test_in_transit_receipt_after_work_order_completion_credits_stock_without_reopening_order():
    reset()
    work_order = maintenance_service.create_manual_work_order("A19", "AV-077")
    transfer = _pending(
        part="AV-077", source="charlie", dest="alpha", quantity=1,
        work_order_id=work_order["id"], for_aircraft="A19",
    )
    transfer_service.approve_transfer(transfer["id"])
    maintenance_service.start_maintenance(work_order["id"])
    maintenance_service.complete_maintenance(work_order["id"])
    before_receipt = snapshot()
    alpha_before = InventoryRepository.find("alpha", "AV-077")["quantity"]

    received = transfer_service.receive_transfer(transfer["id"])

    assert received["status"] == "RECEIVED"
    assert InventoryRepository.find("alpha", "AV-077")["quantity"] == alpha_before + 1
    assert WorkOrderRepository.get(work_order["id"])["status"] == "COMPLETED"
    assert len(snapshot()["audit"]) == len(before_receipt["audit"]) + 1


def test_in_transit_receipt_credits_stock_but_does_not_advance_relinked_work_order():
    reset()
    work_order = maintenance_service.create_manual_work_order("A19", "AV-077")
    WorkOrderRepository.update(work_order["id"], status="WAITING_FOR_RESOURCE")
    transfer = _pending(
        part="AV-077", source="charlie", dest="alpha", quantity=1,
        work_order_id=work_order["id"], for_aircraft="A19",
    )
    transfer_service.approve_transfer(transfer["id"])
    WorkOrderRepository.update(work_order["id"], base_id="bravo")
    before_qty = InventoryRepository.find("alpha", "AV-077")["quantity"]

    received = transfer_service.receive_transfer(transfer["id"])

    assert received["status"] == "RECEIVED"
    assert InventoryRepository.find("alpha", "AV-077")["quantity"] == before_qty + 1
    assert WorkOrderRepository.get(work_order["id"])["status"] == "WAITING_FOR_RESOURCE"


@pytest.mark.parametrize(
    ("field", "value"),
    [("dest_base", "unknown"), ("part_number", "UNKNOWN"), ("quantity", 0), ("condition_pct", 101)],
)
def test_invalid_in_transit_shipment_is_rejected_before_receipt_mutations(field, value):
    reset()
    transfer = _pending()
    transfer_service.approve_transfer(transfer["id"])
    TransferRepository.update(transfer["id"], **{field: value})
    before_receipt = snapshot()

    with pytest.raises(transfer_service.TransferError):
        transfer_service.receive_transfer(transfer["id"])

    assert snapshot() == before_receipt


def test_higher_grade_receipt_does_not_upgrade_existing_unserviceable_pool_or_wo(client):
    from app.services.resource_service import local_availability

    work_order = maintenance_service.create_manual_work_order("A17", "HP-204")
    destination = InventoryRepository.find("alpha", "HP-204")
    InventoryRepository.update(
        destination["id"], quantity=1, reserved=0, minimum_reserve=0,
        condition_pct=20,
    )
    _set_bravo_hp204(quantity=2, condition=80)
    transfer = _pending(
        part="HP-204", source="bravo", dest="alpha", quantity=1,
        work_order_id=work_order["id"], for_aircraft="A17",
    )
    transfer_service.approve_transfer(transfer["id"])

    received = transfer_service.receive_transfer(transfer["id"])

    pooled = InventoryRepository.find("alpha", "HP-204")
    assert received["status"] == "RECEIVED"
    assert (pooled["quantity"], pooled["condition_pct"]) == (2, 20)
    assert local_availability(WorkOrderRepository.get(work_order["id"]))["available"] is False
    assert WorkOrderRepository.get(work_order["id"])["status"] == "WAITING_FOR_RESOURCE"


def test_lower_grade_serviceable_receipt_keeps_conservative_pool_grade():
    reset()
    destination = InventoryRepository.find("alpha", "HP-204")
    InventoryRepository.update(
        destination["id"], quantity=1, reserved=0, minimum_reserve=0,
        condition_pct=90,
    )
    _set_bravo_hp204(quantity=2, condition=50)
    transfer = _pending(quantity=1)
    transfer_service.approve_transfer(transfer["id"])

    transfer_service.receive_transfer(transfer["id"])

    pooled = InventoryRepository.find("alpha", "HP-204")
    assert (pooled["quantity"], pooled["condition_pct"]) == (2, 50)


def test_serviceable_receipt_marks_waiting_work_order_resource_available():
    reset()
    work_order = maintenance_service.create_manual_work_order("A17", "HP-204")
    _set_bravo_hp204(quantity=2, condition=80)
    transfer = _pending(
        part="HP-204", source="bravo", dest="alpha", quantity=1,
        work_order_id=work_order["id"], for_aircraft="A17",
    )
    transfer_service.approve_transfer(transfer["id"])

    transfer_service.receive_transfer(transfer["id"])

    assert WorkOrderRepository.get(work_order["id"])["status"] == "RESOURCE_AVAILABLE"


@pytest.mark.parametrize("destination_change", ["reserve", "condition"])
def test_receipt_does_not_mark_work_order_ready_when_destination_pool_is_unusable(destination_change):
    reset()
    work_order = maintenance_service.create_manual_work_order("A17", "HP-204")
    _set_bravo_hp204(quantity=2, condition=80)
    transfer = _pending(
        part="HP-204", source="bravo", dest="alpha", quantity=1,
        work_order_id=work_order["id"], for_aircraft="A17",
    )
    transfer_service.approve_transfer(transfer["id"])
    destination = InventoryRepository.find("alpha", "HP-204")
    if destination_change == "reserve":
        InventoryRepository.update(destination["id"], minimum_reserve=99)
    else:
        # A lower-grade unit in the destination pool makes the whole pooled
        # line fail the catalog minimum after this otherwise good arrival.
        InventoryRepository.update(destination["id"], quantity=1, condition_pct=20)

    transfer_service.receive_transfer(transfer["id"])

    assert WorkOrderRepository.get(work_order["id"])["status"] == "WAITING_FOR_RESOURCE"
    assert InventoryRepository.find("alpha", "HP-204")["quantity"] >= 1
