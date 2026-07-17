from __future__ import annotations

import argparse
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from data_manager import (
    ExcelWriteLockError,
    add_loose_goods_record,
    add_mould_maintenance_record,
    add_production_change_request,
    complete_mould_maintenance_record,
    clean_import_note_text,
    get_inventory,
    get_mould_maintenance_history,
    get_mould_machine_compatibility,
    get_mould_machine_settings,
    get_mould_hot_runner_settings,
    get_moulds,
    get_product_catalog,
    get_production,
    resolve_mould_status,
    stock_in,
    upsert_mould,
)
from supabase_config import load_settings, service_client, validate_worker_settings
from config import registered_machine_ids


BASE_DIR = Path(__file__).resolve().parent
LOG_DIR = BASE_DIR / "logs"
LOG_FILE = LOG_DIR / "supabase_request_sync.log"
PROCESSING_STALE_MINUTES = 30


def setup_logger() -> logging.Logger:
    LOG_DIR.mkdir(exist_ok=True)
    logger = logging.getLogger("supabase_request_sync")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
        file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
        file_handler.setFormatter(formatter)
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)
    return logger


LOGGER = setup_logger()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def int_quantity(value: Any, field_name: str) -> int:
    number = float(value)
    if number <= 0:
        raise ValueError(f"{field_name} must be greater than zero.")
    if not number.is_integer():
        raise ValueError(f"{field_name} must be a whole number for the current Excel inventory.")
    return int(number)


def number_or_zero(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def first_number(row: pd.Series, columns: list[str]) -> float:
    for column in columns:
        if column in row.index:
            number = number_or_zero(row.get(column))
            if number:
                return number
    return 0.0


def text_value(value: Any) -> str:
    return str(value or "").strip()


def production_notes_text(row: Any) -> str:
    base = text_value(row.get("Notes"))
    pairs = [
        ("Packaging Type", row.get("PackagingType")),
        ("Packaging", row.get("PackagingUnit")),
        ("Carton/Unit/Stack", row.get("CartonUnitStackQty")),
        ("Pallet Qty", row.get("PalletQty")),
        ("Pallet Bag", row.get("PalletBag")),
        ("Pallet Type", row.get("PalletType")),
        ("Wrap Pallet", row.get("WrapPallet")),
        ("Corner Protector", row.get("CornerProtector")),
        ("Extra", row.get("AdditionalPackaging")),
        ("Instructions", row.get("AdditionalInstructions")),
    ]
    generated = " | ".join(f"{label}: {text_value(value)}" for label, value in pairs if text_value(value))
    if base and generated and generated not in base:
        return f"{base} | {generated}"
    return base or generated


def publish_rows_without_blanking(client, table_name: str, rows: list[dict[str, Any]], key_column: str) -> int:
    if not rows:
        LOGGER.warning("No %s rows were generated; existing public data was left unchanged.", table_name)
        return 0

    client.table(table_name).upsert(rows, on_conflict=key_column).execute()
    current_keys = {text_value(row.get(key_column)) for row in rows if text_value(row.get(key_column))}
    if not current_keys:
        LOGGER.warning("%s rows had no valid %s; existing public data was left unchanged.", table_name, key_column)
        return len(rows)

    existing = client.table(table_name).select(key_column).eq("is_active", True).execute()
    for old_row in existing.data or []:
        old_key = text_value(old_row.get(key_column))
        if old_key and old_key not in current_keys:
            client.table(table_name).update({"is_active": False, "updated_at": utc_now()}).eq(key_column, old_key).execute()
    return len(rows)


def find_inventory_product(product_code: str, product_name: str) -> dict[str, str]:
    requested_code = product_code.strip()
    requested_name = product_name.strip()
    if not requested_code and not requested_name:
        raise ValueError("Request product_code/product_name is empty.")

    inventory = get_inventory()
    if requested_code:
        exact_code = inventory[inventory["ProductCode"].str.casefold() == requested_code.casefold()]
        if not exact_code.empty:
            return exact_code.iloc[0].to_dict()
    if requested_name:
        exact_name = inventory[inventory["ProductName"].str.casefold() == requested_name.casefold()]
        if not exact_name.empty:
            return exact_name.iloc[0].to_dict()

    catalog = get_product_catalog()
    catalog_row = pd.DataFrame()
    if requested_code and "Item" in catalog.columns:
        catalog_row = catalog[catalog["Item"].str.casefold() == requested_code.casefold()]
    if catalog_row.empty and requested_name and "ProductDetail" in catalog.columns:
        catalog_row = catalog[catalog["ProductDetail"].str.casefold() == requested_name.casefold()]
    if catalog_row.empty:
        requested = requested_code or requested_name
        raise ValueError(f"Product not found in Inventory.xlsx or ProductCatalog.xlsx: {requested}")

    row = catalog_row.iloc[0]
    product_code = text_value(row.get("Item")) or requested_code or requested_name
    return {
        "ProductCode": product_code,
        "ProductName": text_value(row.get("ProductDetail")) or requested_name or product_code,
        "Unit": "pcs",
        "Location": text_value(row.get("InventoryLocationID")),
        "_create": "TRUE",
    }


def claim_request(client, request_id: str) -> bool:
    response = (
        client.table("stock_in_requests")
        .update({"status": "processing", "error_message": None, "updated_at": utc_now()})
        .eq("id", request_id)
        .eq("status", "pending")
        .execute()
    )
    return bool(response.data)


def reset_stale_processing_requests(client, stale_minutes: int = PROCESSING_STALE_MINUTES) -> int:
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=stale_minutes)).isoformat()
    response = (
        client.table("stock_in_requests")
        .update(
            {
                "status": "pending",
                "error_message": "Previous processing attempt timed out; request returned to pending.",
                "updated_at": utc_now(),
            }
        )
        .eq("status", "processing")
        .lt("updated_at", cutoff)
        .execute()
    )
    count = len(response.data or [])
    if count:
        LOGGER.warning("Returned %s stale processing stock request(s) to pending.", count)
    return count


def mark_request(client, request_id: str, status: str, error: str | None = None) -> None:
    values = {
        "status": status,
        "updated_at": utc_now(),
        "processed_at": utc_now() if status in {"processed", "error"} else None,
        "error_message": error[:1000] if error else None,
    }
    client.table("stock_in_requests").update(values).eq("id", request_id).execute()


def release_request_to_pending(client, request_id: str, error: str) -> None:
    values = {
        "status": "pending",
        "updated_at": utc_now(),
        "error_message": error[:1000],
    }
    client.table("stock_in_requests").update(values).eq("id", request_id).eq("status", "processing").execute()


def process_stock_requests(client) -> tuple[int, int]:
    reset_stale_processing_requests(client)
    response = (
        client.table("stock_in_requests")
        .select(
            "id,client_request_id,product_code,product_name,qty,operator_name,note,created_at,status,"
            "machine_id,schedule_id,mould_number,production_status,pallet_qty,quantity_mode,request_type,loose_status"
        )
        .eq("status", "pending")
        .order("created_at")
        .execute()
    )
    processed = 0
    failed = 0
    for request in response.data or []:
        request_id = str(request["id"])
        client_request_id = text_value(request.get("client_request_id")) or request_id
        if not claim_request(client, request_id):
            continue
        try:
            product = find_inventory_product(text_value(request.get("product_code")), text_value(request.get("product_name")))
            quantity = int_quantity(request.get("qty"), "qty")
            operator = text_value(request.get("operator_name")) or "mobile"
            note = text_value(request.get("note"))
            quantity_mode = text_value(request.get("quantity_mode")) or "custom"
            request_type = text_value(request.get("request_type")) or quantity_mode
            if request_type in {"waiting_for_wrap", "waiting_for_handle"} or quantity_mode in {"waiting_for_wrap", "waiting_for_handle"}:
                loose_status = text_value(request.get("loose_status"))
                if not loose_status:
                    loose_status = "WaitingForWrap" if request_type == "waiting_for_wrap" or quantity_mode == "waiting_for_wrap" else "WaitingForHandle"
                loose_id = add_loose_goods_record(
                    user=f"supabase:{operator}",
                    machine_id=text_value(request.get("machine_id")),
                    schedule_id=text_value(request.get("schedule_id")),
                    product_code=str(product["ProductCode"]),
                    product_name=str(product.get("ProductName", "")),
                    mould_number=text_value(request.get("mould_number")),
                    quantity=quantity,
                    status=loose_status,
                    operator=operator,
                    notes=note or f"Supabase request {client_request_id}",
                    client_request_id=client_request_id,
                    request_type=request_type,
                )
                LOGGER.info("Processed loose goods request %s -> %s qty=%s", client_request_id, loose_id, quantity)
            else:
                stock_in(
                    user=f"supabase:{operator}",
                    product_code=str(product["ProductCode"]),
                    quantity=quantity,
                    remarks=note or f"Supabase request {client_request_id}",
                    product_name=str(product.get("ProductName", "")),
                    unit=str(product.get("Unit", "pcs") or "pcs"),
                    location=str(product.get("Location", "")),
                    create_if_missing=product.get("_create") == "TRUE",
                    machine_id=text_value(request.get("machine_id")),
                    schedule_id=text_value(request.get("schedule_id")),
                    mould_number=text_value(request.get("mould_number")),
                    production_status=text_value(request.get("production_status")),
                    pallet_qty=request.get("pallet_qty"),
                    quantity_mode=quantity_mode,
                    request_type=request_type,
                    client_request_id=client_request_id,
                )
                LOGGER.info("Processed stock request %s for %s qty=%s", client_request_id, product["ProductCode"], quantity)
            mark_request(client, request_id, "processed")
            processed += 1
        except ExcelWriteLockError as exc:
            failed += 1
            release_request_to_pending(client, request_id, str(exc))
            LOGGER.warning("Excel busy; stock request %s returned to pending: %s", client_request_id, exc)
        except Exception as exc:
            failed += 1
            mark_request(client, request_id, "error", str(exc))
            LOGGER.exception("Stock request %s failed", client_request_id)
    return processed, failed


def claim_production_change_request(client, request_id: str) -> bool:
    response = (
        client.table("production_change_requests")
        .update({"status": "processing", "error_message": None, "updated_at": utc_now()})
        .eq("id", request_id)
        .eq("status", "pending")
        .execute()
    )
    return bool(response.data)


def reset_stale_production_change_requests(client, stale_minutes: int = PROCESSING_STALE_MINUTES) -> int:
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=stale_minutes)).isoformat()
    response = (
        client.table("production_change_requests")
        .update(
            {
                "status": "pending",
                "error_message": "Previous processing attempt timed out; request returned to pending.",
                "updated_at": utc_now(),
            }
        )
        .eq("status", "processing")
        .lt("updated_at", cutoff)
        .execute()
    )
    count = len(response.data or [])
    if count:
        LOGGER.warning("Returned %s stale production change request(s) to pending.", count)
    return count


def mark_production_change_request(client, request_id: str, status: str, error: str | None = None) -> None:
    values = {
        "status": status,
        "updated_at": utc_now(),
        "processed_at": utc_now() if status in {"processed", "error"} else None,
        "error_message": error[:1000] if error else None,
    }
    client.table("production_change_requests").update(values).eq("id", request_id).execute()


def release_production_change_request_to_pending(client, request_id: str, error: str) -> None:
    values = {
        "status": "pending",
        "updated_at": utc_now(),
        "error_message": error[:1000],
    }
    client.table("production_change_requests").update(values).eq("id", request_id).eq("status", "processing").execute()


def process_production_change_requests(client) -> tuple[int, int]:
    try:
        reset_stale_production_change_requests(client)
        response = (
            client.table("production_change_requests")
            .select(
                "id,client_request_id,machine_no,old_product_code,old_product_name,old_color,"
                "old_plan_qty,old_completed_qty,old_remaining_qty,new_product_code,new_product_name,"
                "new_color,change_time,reported_completed_qty,reported_remaining_qty,reason,reported_by,"
                "note,photo_url,created_at,status,review_status"
            )
            .eq("status", "pending")
            .order("created_at")
            .execute()
        )
    except Exception as exc:
        LOGGER.warning("Production change request table is not available yet: %s", exc)
        return 0, 0

    processed = 0
    failed = 0
    for request in response.data or []:
        request_id = str(request["id"])
        client_request_id = text_value(request.get("client_request_id")) or request_id
        if not claim_production_change_request(client, request_id):
            continue
        try:
            change_id = add_production_change_request(
                user=f"supabase:{text_value(request.get('reported_by')) or 'mobile'}",
                values={
                    "ChangeID": client_request_id,
                    "ClientRequestID": client_request_id,
                    "CreatedAt": text_value(request.get("created_at")),
                    "MachineNo": text_value(request.get("machine_no")),
                    "OldProductCode": text_value(request.get("old_product_code")),
                    "OldProductName": text_value(request.get("old_product_name")),
                    "OldColor": text_value(request.get("old_color")),
                    "OldPlanQty": text_value(request.get("old_plan_qty")),
                    "OldCompletedQty": text_value(request.get("old_completed_qty")),
                    "OldRemainingQty": text_value(request.get("old_remaining_qty")),
                    "NewProductCode": text_value(request.get("new_product_code")),
                    "NewProductName": text_value(request.get("new_product_name")),
                    "NewColor": text_value(request.get("new_color")),
                    "ChangeTime": text_value(request.get("change_time")),
                    "ReportedCompletedQty": text_value(request.get("reported_completed_qty")),
                    "ReportedRemainingQty": text_value(request.get("reported_remaining_qty")),
                    "Reason": text_value(request.get("reason")),
                    "ReportedBy": text_value(request.get("reported_by")) or "mobile",
                    "Note": text_value(request.get("note")),
                    "PhotoPath": text_value(request.get("photo_url")),
                    "Status": "Pending Review",
                },
            )
            LOGGER.info("Imported production change request %s -> %s", client_request_id, change_id)
            mark_production_change_request(client, request_id, "processed")
            processed += 1
        except ExcelWriteLockError as exc:
            failed += 1
            release_production_change_request_to_pending(client, request_id, str(exc))
            LOGGER.warning("Excel busy; production change request %s returned to pending: %s", client_request_id, exc)
        except Exception as exc:
            failed += 1
            mark_production_change_request(client, request_id, "error", str(exc))
            LOGGER.exception("Production change request %s failed", client_request_id)
    return processed, failed


def public_product_rows() -> list[dict[str, Any]]:
    catalog = get_product_catalog()
    rows: list[dict[str, Any]] = []
    if not catalog.empty:
        for _, row in catalog.iterrows():
            code = text_value(row.get("Item"))
            name = text_value(row.get("ProductDetail")) or code
            if not code and not name:
                continue
            label = text_value(row.get("HasLabel"))
            search_text = " ".join(
                text_value(row.get(column))
                for column in [
                    "Item",
                    "ProductDetail",
                    "HasLabel",
                    "Colour",
                    "Size",
                    "Part",
                    "MainMaterial",
                    "AdditionalInstructions",
                ]
            )
            rows.append(
                {
                    "product_code": code or name,
                    "product_name": name,
                    "label": label,
                    "pallet_qty": first_number(row, ["PalletQty", "Pallet Qty", "pallet_qty", "palletQty"]) or None,
                    "search_text": search_text,
                    "is_active": True,
                    "updated_at": utc_now(),
                }
            )
    if rows:
        unique: dict[str, dict[str, Any]] = {}
        for row in rows:
            unique[row["product_code"]] = row
        return sorted(unique.values(), key=lambda item: str(item.get("product_name", "")).casefold())

    inventory = get_inventory()
    for _, row in inventory.iterrows():
        code = text_value(row.get("ProductCode"))
        name = text_value(row.get("ProductName")) or code
        if not code and not name:
            continue
        rows.append(
            {
                "product_code": code or name,
                "product_name": name,
                "label": "",
                "pallet_qty": None,
                "search_text": f"{code} {name}",
                "is_active": True,
                "updated_at": utc_now(),
            }
        )
    return sorted(rows, key=lambda item: str(item.get("product_name", "")).casefold())


def publish_products(client) -> int:
    rows = public_product_rows()
    publish_rows_without_blanking(client, "mobile_public_products", rows, "product_code")
    LOGGER.info("Published %s mobile products", len(rows))
    return len(rows)


def machine_public_rows() -> list[dict[str, Any]]:
    production = get_production()
    rows = []
    for machine_id in registered_machine_ids(production):
        group = production[production["MachineID"].astype(str).str.strip() == machine_id]
        if group.empty:
            rows.append(
                {
                    "machine_id": machine_id,
                    "machine_name": machine_id,
                    "running_product": "No running production plan",
                    "product_code": "",
                    "product_name": "No running production plan",
                    "planned_qty": 0,
                    "completed_qty": 0,
                    "remaining_qty": 0,
                    "status": "No Plan",
                    "mould_number": "",
                    "material": "",
                    "material_location": "",
                    "colour_masterbatch": "",
                    "operator_name": "",
                    "pallet_qty": None,
                    "notes": "",
                    "is_active": True,
                    "updated_at": utc_now(),
                }
            )
            continue
        running = group[group["Status"].str.casefold() == "running"]
        visible = running if not running.empty else group.head(1)
        planned = sum(number_or_zero(value) for value in visible["PlannedQty"].tolist())
        completed = sum(number_or_zero(value) for value in visible["CompletedQty"].tolist())
        product_codes = [text_value(value) for value in visible["ProductCode"].tolist() if text_value(value)]
        products = [text_value(value) for value in visible["ProductName"].tolist() if text_value(value)]
        machine_names = [text_value(value) for value in visible["MachineName"].tolist() if text_value(value)]
        mould_numbers = [text_value(value) for value in visible["MouldNumber"].tolist() if text_value(value)]
        materials = [text_value(value) for value in visible["Material"].tolist() if text_value(value)]
        material_locations = [text_value(value) for value in visible["MaterialLocation"].tolist() if text_value(value)]
        colours = [text_value(value) for value in visible["ColourMasterbatch"].tolist() if text_value(value)]
        notes = [production_notes_text(row) for _, row in visible.iterrows() if production_notes_text(row)]
        status_values = [text_value(value) for value in visible["Status"].tolist() if text_value(value)]
        pallet_qty_values = [number_or_zero(value) for value in visible["PalletQty"].tolist() if number_or_zero(value)]
        status = " / ".join(dict.fromkeys(status_values)) or "No Plan"
        running_product = " / ".join(dict.fromkeys(products)) or "No running production plan"
        rows.append(
            {
                "machine_id": machine_id,
                "machine_name": " / ".join(dict.fromkeys(machine_names)),
                "running_product": running_product,
                "product_code": " / ".join(dict.fromkeys(product_codes)),
                "product_name": running_product,
                "planned_qty": planned,
                "completed_qty": completed,
                "remaining_qty": max(planned - completed, 0),
                "status": status,
                "mould_number": " / ".join(dict.fromkeys(mould_numbers)),
                "material": " / ".join(dict.fromkeys(materials)),
                "material_location": " / ".join(dict.fromkeys(material_locations)),
                "colour_masterbatch": " / ".join(dict.fromkeys(colours)),
                "operator_name": "",
                "pallet_qty": pallet_qty_values[0] if pallet_qty_values else None,
                "notes": " | ".join(dict.fromkeys(notes)),
                "is_active": True,
                "updated_at": utc_now(),
            }
        )
    return rows


def publish_machines(client) -> int:
    rows = machine_public_rows()
    publish_rows_without_blanking(client, "mobile_public_machines", rows, "machine_id")
    LOGGER.info("Published %s public machines", len(rows))
    return len(rows)


def production_item_rows() -> list[dict[str, Any]]:
    production = get_production()
    rows = []
    for _, row in production.iterrows():
        status = text_value(row.get("Status"))
        if status.casefold() == "queued":
            status = "Next"
        if status not in {"Running", "Next", "Planned"}:
            continue
        rows.append(
            {
                "schedule_id": text_value(row.get("ScheduleID")),
                "machine_id": text_value(row.get("MachineID")),
                "machine_name": text_value(row.get("MachineName")),
                "sequence": int(number_or_zero(row.get("Sequence"))),
                "status": status,
                "product_code": text_value(row.get("ProductCode")),
                "product_name": text_value(row.get("ProductName")),
                "mould_number": text_value(row.get("MouldNumber")),
                "material": text_value(row.get("Material")),
                "material_location": text_value(row.get("MaterialLocation")),
                "colour_masterbatch": text_value(row.get("ColourMasterbatch")),
                "operator_name": "",
                "notes": production_notes_text(row),
                "planned_qty": number_or_zero(row.get("PlannedQty")),
                "completed_qty": number_or_zero(row.get("CompletedQty")),
                "pallet_qty": first_number(row, ["PalletQty", "Pallet Qty", "pallet_qty", "palletQty"]) or None,
                "updated_at": utc_now(),
                "is_active": True,
            }
        )
    return rows


def publish_production_items(client) -> int:
    rows = production_item_rows()
    publish_rows_without_blanking(client, "mobile_public_production_items", rows, "schedule_id")
    return len(rows)



def claim_mould_change_request(client, request_id: str):
    return (
        client.table("mould_change_requests")
        .update({"status": "processing", "error_message": None, "updated_at": utc_now()})
        .eq("id", request_id)
        .eq("status", "pending")
        .execute()
    )


def mark_mould_change_request(client, request_id: str, status: str, error: str | None = None) -> None:
    values = {
        "status": status,
        "error_message": error,
        "processed_at": utc_now() if status in {"processed", "error"} else None,
        "updated_at": utc_now(),
    }
    client.table("mould_change_requests").update(values).eq("id", request_id).execute()


def release_mould_change_request_to_pending(client, request_id: str, error: str) -> None:
    values = {
        "status": "pending",
        "error_message": error,
        "updated_at": utc_now(),
    }
    client.table("mould_change_requests").update(values).eq("id", request_id).eq("status", "processing").execute()


def process_mould_change_requests(client) -> tuple[int, int]:
    try:
        response = (
            client.table("mould_change_requests")
            .select("*")
            .eq("status", "pending")
            .order("created_at")
            .limit(25)
            .execute()
        )
    except Exception:
        LOGGER.exception("Unable to fetch mould change requests")
        return 0, 1
    processed = 0
    failed = 0
    for request in response.data or []:
        request_id = request.get("id")
        client_request_id = text_value(request.get("client_request_id"))
        try:
            claim_mould_change_request(client, request_id)
            request_type = text_value(request.get("request_type")).casefold()
            mould_number = text_value(request.get("mould_number"))
            submitted_by = text_value(request.get("submitted_by")) or "cloud-tech-manager"
            if not mould_number:
                raise ValueError("mould_number is required.")
            if request_type == "update_notes":
                upsert_mould(
                    submitted_by,
                    mould_number,
                    {
                        "Notes": text_value(request.get("note")),
                    },
                )
            elif request_type == "update_basic":
                values = {
                    "MouldName": text_value(request.get("mould_name")),
                    "MouldType": text_value(request.get("mould_type")),
                    "MouldSize": text_value(request.get("mould_size")),
                    "MouldSeries": text_value(request.get("mould_series")),
                    "StorageLocation": text_value(request.get("storage_location")),
                    "Notes": text_value(request.get("note")),
                }
                upsert_mould(submitted_by, mould_number, values)
            elif request_type == "add_maintenance":
                add_mould_maintenance_record(
                    submitted_by,
                    mould_number,
                    text_value(request.get("technician_name")) or submitted_by,
                    text_value(request.get("maintenance_content")),
                    set_maintenance=bool(request.get("set_maintenance", True)),
                )
            elif request_type == "complete_maintenance":
                history = get_mould_maintenance_history()
                open_rows = history[
                    history["MouldNumber"].astype(str).str.casefold().eq(mould_number.casefold())
                    & ~history["Status"].astype(str).str.casefold().isin({"completed", "closed", "cancelled"})
                    & ~history["IsDeleted"].astype(str).str.casefold().isin({"true", "yes", "1"})
                ].copy()
                if open_rows.empty:
                    raise ValueError(f"No open maintenance record found for mould {mould_number}.")
                open_rows = open_rows.sort_values("CreatedAt", ascending=False)
                complete_mould_maintenance_record(submitted_by, str(open_rows.iloc[0].get("MaintenanceID")), text_value(request.get("note")))
            else:
                raise ValueError(f"Unsupported mould request_type: {request_type}")
            mark_mould_change_request(client, request_id, "processed")
            processed += 1
            LOGGER.info("Processed mould change request %s type=%s mould=%s", client_request_id, request_type, mould_number)
        except ExcelWriteLockError as exc:
            release_mould_change_request_to_pending(client, request_id, str(exc))
            LOGGER.warning("Excel busy; mould request %s returned to pending: %s", client_request_id, exc)
        except Exception as exc:
            mark_mould_change_request(client, request_id, "error", str(exc))
            failed += 1
            LOGGER.exception("Failed mould change request %s", client_request_id)
    return processed, failed

def public_mould_rows() -> list[dict[str, Any]]:
    moulds = get_moulds()
    rows = []
    for _, row in moulds.iterrows():
        number = text_value(row.get("MouldNumber"))
        if not number:
            continue
        status_info = resolve_mould_status(number)
        rows.append(
            {
                "mould_number": number,
                "mould_name": text_value(row.get("MouldName")) or text_value(row.get("AssociatedProduct")),
                "mould_type": text_value(row.get("MouldType")),
                "mould_size": text_value(row.get("MouldSize")),
                "mould_series": text_value(row.get("MouldSeries")),
                "storage_location": text_value(row.get("StorageLocation")),
                "status": text_value(row.get("Status")) or "Available",
                "computed_status": status_info.get("status", ""),
                "computed_location": status_info.get("location", ""),
                "maintenance_open": status_info.get("status") == "maintenance",
                "issue_description": text_value(row.get("IssueDescription")),
                "associated_products": text_value(row.get("AssociatedProduct")),
                "notes": text_value(clean_import_note_text(row.get("Notes"))) or text_value(clean_import_note_text(row.get("MaintenanceNotes"))),
                "updated_at": utc_now(),
                "is_active": str(row.get("Active", "TRUE")).strip().lower() not in {"false", "no", "0"},
            }
        )
    return rows



def bool_from_text(value: Any, default: bool = False) -> bool:
    text = str(value or "").strip().casefold()
    if not text:
        return default
    return text in {"true", "yes", "y", "1", "active"}


def setting_float_or_none(value: Any) -> float | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def mould_machine_compatibility_public_rows() -> list[dict[str, Any]]:
    compatibility = get_mould_machine_compatibility()
    rows: list[dict[str, Any]] = []
    for _, row in compatibility.iterrows():
        mould_number = text_value(row.get("MouldNumber"))
        machine_id = text_value(row.get("MachineID"))
        if not mould_number or not machine_id:
            continue
        rows.append(
            {
                "snapshot_key": f"{mould_number}|{machine_id}",
                "mould_number": mould_number,
                "machine_id": machine_id,
                "is_preferred": bool_from_text(row.get("IsPreferred")),
                "is_active": bool_from_text(row.get("IsActive"), default=True),
                "notes": text_value(row.get("Notes")),
                "updated_at": utc_now(),
            }
        )
    return rows


def mould_machine_settings_public_rows() -> list[dict[str, Any]]:
    settings = get_mould_machine_settings()
    hot_runner = get_mould_hot_runner_settings()
    rows: list[dict[str, Any]] = []
    if settings.empty:
        return rows
    active = settings[settings["IsActive"].astype(str).str.casefold().isin({"true", "yes", "1"})].copy()
    for _, row in active.iterrows():
        mould_number = text_value(row.get("MouldNumber"))
        machine_id = text_value(row.get("MachineID"))
        setting_id = text_value(row.get("SettingID"))
        if not mould_number or not machine_id:
            continue
        injection_summary = [
            {
                "stage": stage,
                "pressure": setting_float_or_none(row.get(f"injection_stage_{stage}_pressure")),
                "speed": setting_float_or_none(row.get(f"injection_stage_{stage}_speed")),
                "position": setting_float_or_none(row.get(f"injection_stage_{stage}_position")),
            }
            for stage in range(1, 6)
        ]
        holding_summary = [
            {
                "stage": stage,
                "pressure": setting_float_or_none(row.get(f"holding_stage_{stage}_pressure")),
                "time": setting_float_or_none(row.get(f"holding_stage_{stage}_time")),
                "speed": setting_float_or_none(row.get(f"holding_stage_{stage}_speed")),
            }
            for stage in range(1, 4)
        ]
        temperature_summary = {
            "barrel_1": setting_float_or_none(row.get("barrel_temperature_1")),
            "barrel_2": setting_float_or_none(row.get("barrel_temperature_2")),
            "barrel_3": setting_float_or_none(row.get("barrel_temperature_3")),
            "barrel_4": setting_float_or_none(row.get("barrel_temperature_4")),
            "nozzle": setting_float_or_none(row.get("nozzle_temperature")),
        }
        hot_rows = []
        if setting_id and not hot_runner.empty:
            related = hot_runner[hot_runner["SettingID"].astype(str).eq(setting_id)].copy()
            for _, hot_row in related.iterrows():
                hot_rows.append(
                    {
                        "zone_number": text_value(hot_row.get("ZoneNumber")),
                        "zone_name": text_value(hot_row.get("ZoneName")),
                        "temperature": setting_float_or_none(hot_row.get("Temperature")),
                    }
                )
        rows.append(
            {
                "snapshot_key": f"{mould_number}|{machine_id}",
                "mould_number": mould_number,
                "machine_id": machine_id,
                "version": int(number_or_zero(row.get("Version"))),
                "cycle_time_seconds": setting_float_or_none(row.get("cycle_time_seconds")),
                "core_time_summary": {
                    "injection_time_seconds": setting_float_or_none(row.get("injection_time_seconds")),
                    "holding_time_seconds": setting_float_or_none(row.get("holding_time_seconds")),
                    "cooling_time_seconds": setting_float_or_none(row.get("cooling_time_seconds")),
                    "cycle_time_seconds": setting_float_or_none(row.get("cycle_time_seconds")),
                },
                "injection_summary": injection_summary,
                "holding_summary": holding_summary,
                "temperature_summary": temperature_summary,
                "hot_runner_summary": hot_rows,
                "notes": text_value(clean_import_note_text(row.get("Notes"))),
                "updated_at": utc_now(),
                "updated_by": text_value(row.get("UpdatedBy")),
                "is_active": True,
            }
        )
    return rows


def publish_mould_parameter_snapshots(client) -> tuple[int, int]:
    compatibility_rows = mould_machine_compatibility_public_rows()
    settings_rows = mould_machine_settings_public_rows()
    publish_rows_without_blanking(client, "mobile_public_mould_machine_compatibility", compatibility_rows, "snapshot_key")
    publish_rows_without_blanking(client, "mobile_public_mould_machine_settings", settings_rows, "snapshot_key")
    LOGGER.info("Published %s mould-machine compatibility rows and %s parameter rows", len(compatibility_rows), len(settings_rows))
    return len(compatibility_rows), len(settings_rows)

def publish_moulds(client) -> int:
    rows = public_mould_rows()
    publish_rows_without_blanking(client, "mobile_public_moulds", rows, "mould_number")
    return len(rows)


def run_sync(publish_only: bool = False) -> dict[str, int]:
    settings = load_settings()
    validate_worker_settings(settings)
    client = service_client(settings)
    results = {
        "stock_processed": 0,
        "stock_failed": 0,
        "production_change_processed": 0,
        "production_change_failed": 0,
        "mould_change_processed": 0,
        "mould_change_failed": 0,
        "products_published": 0,
        "machines_published": 0,
        "production_items_published": 0,
        "moulds_published": 0,
        "mould_machine_compatibility_published": 0,
        "mould_machine_settings_published": 0,
    }
    if not publish_only:
        results["stock_processed"], results["stock_failed"] = process_stock_requests(client)
        results["production_change_processed"], results["production_change_failed"] = process_production_change_requests(client)
        results["mould_change_processed"], results["mould_change_failed"] = process_mould_change_requests(client)
    results["products_published"] = publish_products(client)
    results["machines_published"] = publish_machines(client)
    results["production_items_published"] = publish_production_items(client)
    results["moulds_published"] = publish_moulds(client)
    results["mould_machine_compatibility_published"], results["mould_machine_settings_published"] = publish_mould_parameter_snapshots(client)
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Synchronize Supabase mobile requests into local Excel files.")
    parser.add_argument("--publish-only", action="store_true", help="Only publish public product and machine lists.")
    parser.add_argument("--check-config", action="store_true", help="Validate .env without contacting Supabase.")
    args = parser.parse_args()

    try:
        settings = load_settings()
        validate_worker_settings(settings)
        if args.check_config:
            print("Supabase worker configuration is present.")
            return 0
        results = run_sync(publish_only=args.publish_only)
        LOGGER.info("Sync complete: %s", results)
        print(results)
        return 0
    except Exception:
        LOGGER.exception("Sync run failed")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
