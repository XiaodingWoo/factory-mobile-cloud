from __future__ import annotations

import os
from datetime import datetime, timezone
from html import escape
from urllib.parse import urlencode
from uuid import uuid4

import streamlit as st
import streamlit.components.v1 as components
from postgrest.types import ReturnMethod

from mobile_cloud_config import (
    MobileCloudSettings,
    load_mobile_cloud_settings,
    mobile_cloud_client,
    validate_mobile_cloud_settings,
)


st.set_page_config(
    page_title="Factory Mobile Cloud",
    layout="centered",
    initial_sidebar_state="collapsed",
)


CLOUD_ENV_NAMES = ("SUPABASE_URL", "SUPABASE_ANON_KEY", "MOBILE_PIN")


def load_cloud_environment() -> None:
    for name in CLOUD_ENV_NAMES:
        if os.getenv(name):
            continue
        try:
            secret_value = st.secrets.get(name, "")
        except Exception:
            secret_value = ""
        if secret_value:
            os.environ[name] = str(secret_value)


def inject_css() -> None:
    components.html(
        """
        <script>
        const doc = window.parent.document;
        let viewport = doc.querySelector('meta[name="viewport"]');
        if (!viewport) {
            viewport = doc.createElement('meta');
            viewport.setAttribute('name', 'viewport');
            doc.head.appendChild(viewport);
        }
        viewport.setAttribute('content', 'width=device-width, initial-scale=1.0');
        const tunePin = () => {
            doc.querySelectorAll('input[type="password"]').forEach((input) => {
                input.setAttribute('inputmode', 'numeric');
                input.setAttribute('autocomplete', 'one-time-code');
                input.setAttribute('pattern', '[0-9]*');
            });
        };
        tunePin();
        new MutationObserver(tunePin).observe(doc.body, { childList: true, subtree: true });
        </script>
        """,
        height=0,
        width=0,
    )
    st.markdown(
        """
        <style>
        html, body, .stApp {
            max-width: 100%;
            overflow-x: hidden;
            -webkit-text-size-adjust: 100%;
        }
        * { box-sizing: border-box; }
        [data-testid="stHeader"], [data-testid="stSidebar"], [data-testid="stToolbar"],
        [data-testid="stDecoration"], [data-testid="stStatusWidget"], #MainMenu {
            display: none !important;
        }
        .stApp { background: #f4f6f8; }
        .block-container {
            width: 100%;
            max-width: 520px;
            padding: 12px 12px 1.4rem;
        }
        h1 {
            color: #111827;
            font-size: 1.55rem !important;
            line-height: 1.18;
            margin: 0.1rem 0 0.65rem;
            letter-spacing: 0;
        }
        h2, h3 {
            letter-spacing: 0;
        }
        button,
        input,
        textarea,
        [role="button"],
        [role="combobox"] {
            font-size: 16px !important;
        }
        .stButton > button, div[data-testid="stFormSubmitButton"] button {
            width: 100%;
            min-height: 52px;
            border-radius: 10px;
            font-size: 1rem;
            font-weight: 750;
        }
        .stTextInput input, .stNumberInput input, .stSelectbox div[data-baseweb="select"], .stTextArea textarea {
            min-height: 50px;
            font-size: 16px !important;
            border-radius: 10px;
        }
        .stTextArea textarea { min-height: 88px; }
        div[data-testid="stVerticalBlock"] { gap: 0.55rem; }
        .public-card, .success-card, .summary-card {
            background: #ffffff;
            border: 1px solid #d9dee7;
            border-radius: 10px;
            padding: 0.82rem;
            margin: 0.6rem 0;
            box-shadow: 0 1px 2px rgba(15, 23, 42, 0.05);
        }
        .public-card { border-left: 5px solid #64748b; }
        .public-card.status-running { border-left-color: #16a34a; }
        .public-card.status-paused, .public-card.status-stopped, .public-card.status-finished {
            border-left-color: #dc2626;
        }
        .public-card.status-setup, .public-card.status-changeover {
            border-left-color: #f59e0b;
        }
        .public-card.status-maintenance { border-left-color: #2563eb; }
        .label {
            color: #6b7280;
            font-size: 0.86rem;
            margin-top: 0.38rem;
        }
        .value {
            color: #111827;
            font-size: 1rem;
            font-weight: 760;
            overflow-wrap: anywhere;
        }
        .machine-title {
            display: flex;
            justify-content: space-between;
            gap: 0.6rem;
            align-items: flex-start;
        }
        .machine-id {
            color: #111827;
            font-size: 1.36rem;
            line-height: 1.15;
            font-weight: 850;
        }
        .status-badge {
            flex: 0 0 auto;
            border-radius: 999px;
            padding: 0.3rem 0.62rem;
            font-size: 0.84rem;
            font-weight: 850;
            line-height: 1.1;
            white-space: nowrap;
        }
        .status-badge.status-running {
            background: #dcfce7;
            border: 1px solid #86efac;
            color: #166534;
        }
        .status-badge.status-paused, .status-badge.status-stopped, .status-badge.status-finished {
            background: #fee2e2;
            border: 1px solid #fecaca;
            color: #991b1b;
        }
        .status-badge.status-setup, .status-badge.status-changeover {
            background: #fef3c7;
            border: 1px solid #fde68a;
            color: #92400e;
        }
        .status-badge.status-maintenance, .status-badge.status-no-plan {
            background: #e0f2fe;
            border: 1px solid #bae6fd;
            color: #075985;
        }
        .metrics {
            display: grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            gap: 0.45rem;
            margin-top: 0.65rem;
        }
        .metric {
            background: #f8fafc;
            border: 1px solid #e5e7eb;
            border-radius: 8px;
            padding: 0.55rem;
            min-width: 0;
        }
        .metric b {
            display: block;
            margin-top: 0.2rem;
            overflow-wrap: anywhere;
        }
        .machine-button-grid {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 0.55rem;
            margin-top: 0.6rem;
        }
        .machine-button {
            display: block;
            min-height: 56px;
            padding: 0.7rem 0.55rem;
            text-align: center;
            text-decoration: none;
            color: #111827;
            background: #ffffff;
            border: 1px solid #d9dee7;
            border-radius: 10px;
            font-size: 1.05rem;
            font-weight: 850;
        }
        .machine-button small {
            display: block;
            color: #6b7280;
            font-size: 0.78rem;
            font-weight: 750;
            margin-top: 0.15rem;
        }
        .summary-card {
            border-left: 5px solid #2563eb;
        }
        .success-card {
            border-left: 5px solid #16a34a;
        }
        .sticky-submit {
            position: sticky;
            bottom: calc(0.45rem + env(safe-area-inset-bottom));
            z-index: 20;
            padding: 0.45rem 0 0.25rem;
            background: linear-gradient(180deg, rgba(244, 246, 248, 0.65), #f4f6f8 38%);
        }
        .stale-warning {
            margin-top: 0.65rem;
            padding: 0.65rem;
            border-radius: 8px;
            border: 1px solid #fed7aa;
            background: #fff7ed;
            color: #9a3412;
            font-weight: 750;
        }
        @media (max-width: 360px) {
            .block-container { padding-left: 10px; padding-right: 10px; }
            .metrics, .machine-button-grid { grid-template-columns: 1fr; }
            h1 { font-size: 1.38rem !important; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def query_value(name: str, default: str = "") -> str:
    value = st.query_params.get(name, default)
    if isinstance(value, list):
        return value[0] if value else default
    return str(value or default)


def require_pin(mobile_pin: str) -> bool:
    if st.session_state.get("mobile_pin_ok"):
        return True
    st.title("Factory Mobile")
    with st.form("pin_form"):
        pin = st.text_input("PIN", type="password", placeholder="Enter mobile PIN")
        submitted = st.form_submit_button("Continue")
    if submitted:
        if pin == mobile_pin:
            st.session_state["mobile_pin_ok"] = True
            st.rerun()
        else:
            st.error("Incorrect PIN.")
    return False


@st.cache_data(ttl=60)
def load_products(settings: MobileCloudSettings) -> list[dict]:
    client = mobile_cloud_client(settings)
    response = (
        client.table("mobile_public_products")
        .select("product_code,product_name,label,search_text,is_active")
        .eq("is_active", True)
        .order("product_name")
        .execute()
    )
    return response.data or []


@st.cache_data(ttl=30)
def load_machines(settings: MobileCloudSettings) -> list[dict]:
    client = mobile_cloud_client(settings)
    response = (
        client.table("mobile_public_machines")
        .select(
            "machine_id,running_product,product_code,product_name,planned_qty,completed_qty,"
            "remaining_qty,status,mould_number,material,colour_masterbatch,notes,updated_at,is_active"
        )
        .eq("is_active", True)
        .order("machine_id")
        .execute()
    )
    return response.data or []


def reset_stock_request() -> None:
    st.session_state["stock_client_request_id"] = str(uuid4())
    st.session_state["stock_request_success"] = None
    st.session_state["stock_last_submitted_id"] = ""


def current_request_id() -> str:
    if not st.session_state.get("stock_client_request_id"):
        reset_stock_request()
    return str(st.session_state["stock_client_request_id"])


def int_quantity(value: object) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("Quantity must be a whole number.") from exc
    if number <= 0:
        raise ValueError("Quantity must be greater than zero.")
    return number


def product_label(product: dict) -> str:
    code = str(product.get("product_code") or "").strip()
    name = str(product.get("product_name") or "").strip()
    label = str(product.get("label") or "").strip()
    parts = [part for part in [code, name] if part]
    text = " - ".join(parts) if parts else name or code or "Unnamed product"
    if label:
        text = f"{text} | {label}"
    return text


def filter_products(products: list[dict], keyword: str) -> list[dict]:
    words = [word.casefold() for word in keyword.replace(",", " ").split() if word.strip()]
    if not words:
        return products
    filtered = []
    for product in products:
        haystack = " ".join(
            str(product.get(field) or "")
            for field in ["product_code", "product_name", "label", "search_text"]
        ).casefold()
        if all(word in haystack for word in words):
            filtered.append(product)
    return filtered


def duplicate_error(exc: Exception) -> bool:
    text = str(exc).casefold()
    return "duplicate" in text or "unique" in text or "23505" in text or "client_request_id" in text


def now_display() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def show_success_card(summary: dict) -> None:
    st.markdown(
        f"""
        <div class="success-card">
            <div class="value">Pending - waiting for office PC sync</div>
            <div class="label">Request ID</div>
            <div class="value">{escape(summary.get("request_id", ""))}</div>
            <div class="label">Product</div>
            <div class="value">{escape(summary.get("product", ""))}</div>
            <div class="label">Quantity</div>
            <div class="value">{escape(str(summary.get("quantity", "")))}</div>
            <div class="label">Operator</div>
            <div class="value">{escape(summary.get("operator", ""))}</div>
            <div class="label">Submitted at</div>
            <div class="value">{escape(summary.get("submitted_at", ""))}</div>
            <div class="label">Status</div>
            <div class="value">{escape(summary.get("status", "pending"))}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def stock_in_request_page(settings: MobileCloudSettings) -> None:
    st.title("Stock-In Request")
    try:
        products = load_products(settings)
    except Exception:
        st.error("Unable to load products from Supabase. Check network, schema migration, and anon key.")
        return
    if not products:
        st.warning("No active products are available. Run the local sync worker first.")
        return

    success_summary = st.session_state.get("stock_request_success")
    if success_summary:
        show_success_card(success_summary)
        if st.button("Create another request"):
            reset_stock_request()
            st.rerun()
        return

    keyword = st.text_input("Search product code / name / label", placeholder="Type product code, name, label")
    filtered_products = filter_products(products, keyword)
    if not filtered_products:
        st.warning("No product matches this search.")
        return

    options = {product_label(product): product for product in filtered_products}
    selected_label = st.selectbox("Product", list(options.keys()))
    selected_product = options[selected_label]

    if "stock_qty" not in st.session_state:
        st.session_state["stock_qty"] = 1

    def add_qty(amount: int) -> None:
        st.session_state["stock_qty"] = max(int(st.session_state.get("stock_qty") or 0) + amount, 0)

    def clear_qty() -> None:
        st.session_state["stock_qty"] = 0

    qty_cols = st.columns(4)
    qty_cols[0].button("+1", on_click=add_qty, args=(1,))
    qty_cols[1].button("+10", on_click=add_qty, args=(10,))
    qty_cols[2].button("+100", on_click=add_qty, args=(100,))
    qty_cols[3].button("Clear", on_click=clear_qty)

    qty = st.number_input("Quantity", min_value=0, step=1, value=int(st.session_state["stock_qty"]), key="stock_qty")
    operator_name = st.text_input("Operator name", placeholder="Required")
    note = st.text_area("Note (optional)")

    request_id = current_request_id()
    summary_note = note.strip() or "-"
    st.markdown(
        f"""
        <div class="summary-card">
            <div class="label">Confirm product</div>
            <div class="value">{escape(selected_label)}</div>
            <div class="label">Quantity</div>
            <div class="value">{escape(str(qty))}</div>
            <div class="label">Operator</div>
            <div class="value">{escape(operator_name.strip() or "Required")}</div>
            <div class="label">Note</div>
            <div class="value">{escape(summary_note)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown('<div class="sticky-submit">', unsafe_allow_html=True)
    submitted = st.button("Submit Request", type="primary")
    st.markdown("</div>", unsafe_allow_html=True)

    if not submitted:
        return
    if st.session_state.get("stock_last_submitted_id") == request_id:
        st.warning("This request was already submitted. Please wait for office PC sync.")
        return

    try:
        quantity = int_quantity(qty)
        operator = operator_name.strip()
        if not operator:
            raise ValueError("Operator name is required.")

        st.session_state["stock_last_submitted_id"] = request_id
        client = mobile_cloud_client(settings)
        product_code = str(selected_product.get("product_code") or "").strip()
        product_name = str(selected_product.get("product_name") or "").strip()
        client.table("stock_in_requests").insert(
            {
                "client_request_id": request_id,
                "product_code": product_code or None,
                "product_name": product_name,
                "qty": quantity,
                "operator_name": operator,
                "note": note.strip() or None,
                "source": "mobile",
                "status": "pending",
            },
            returning=ReturnMethod.minimal,
        ).execute()
        st.session_state["stock_request_success"] = {
            "request_id": request_id,
            "product": selected_label,
            "quantity": quantity,
            "operator": operator,
            "submitted_at": now_display(),
            "status": "pending",
        }
        st.rerun()
    except ValueError as exc:
        st.session_state["stock_last_submitted_id"] = ""
        st.error(str(exc))
    except Exception:
        if duplicate_error(exc):
            st.warning("This request was already received. It will not create a second stock-in request.")
            st.session_state["stock_request_success"] = {
                "request_id": request_id,
                "product": selected_label,
                "quantity": qty,
                "operator": operator_name.strip(),
                "submitted_at": now_display(),
                "status": "pending",
            }
            st.rerun()
            return
        st.session_state["stock_last_submitted_id"] = ""
        st.error("Request failed. Check network and try again, or contact the supervisor.")


def status_class(status: object) -> str:
    text = str(status or "").strip().casefold()
    if "running" in text:
        return "status-running"
    if "pause" in text:
        return "status-paused"
    if "stop" in text:
        return "status-stopped"
    if "finish" in text or "complete" in text:
        return "status-finished"
    if "setup" in text:
        return "status-setup"
    if "change" in text:
        return "status-changeover"
    if "maintenance" in text:
        return "status-maintenance"
    return "status-no-plan"


def parse_updated_at(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def stale_minutes(updated_at: object) -> int | None:
    parsed = parse_updated_at(updated_at)
    if parsed is None:
        return None
    return int((datetime.now(timezone.utc) - parsed).total_seconds() // 60)


def machine_card(machine: dict) -> None:
    machine_id = escape(str(machine.get("machine_id") or "-"))
    product_name = escape(str(machine.get("product_name") or machine.get("running_product") or "No running production plan"))
    product_code = escape(str(machine.get("product_code") or "-"))
    mould_number = escape(str(machine.get("mould_number") or "-"))
    material = escape(str(machine.get("material") or "-"))
    colour = escape(str(machine.get("colour_masterbatch") or "-"))
    status = str(machine.get("status") or "No Plan")
    status_css = status_class(status)
    notes = escape(str(machine.get("notes") or "-"))
    updated_at = str(machine.get("updated_at") or "-")
    minutes_old = stale_minutes(updated_at)
    stale_block = ""
    if minutes_old is None:
        stale_block = '<div class="stale-warning">Last update time is unavailable.</div>'
    elif minutes_old > 10:
        stale_block = f'<div class="stale-warning">Stale warning: last update was {minutes_old} minutes ago.</div>'

    st.markdown(
        f"""
        <div class="summary-card">
            <div class="label">Source</div>
            <div class="value">Supabase cloud snapshot</div>
            <div class="label">Last cloud update</div>
            <div class="value">{escape(updated_at)}</div>
        </div>
        <div class="public-card {status_css}">
            <div class="machine-title">
                <div>
                    <div class="label">Machine</div>
                    <div class="machine-id">{machine_id}</div>
                </div>
                <div class="status-badge {status_css}">{escape(status)}</div>
            </div>
            <div class="label">Product Name</div>
            <div class="value">{product_name}</div>
            <div class="label">Product Code</div>
            <div class="value">{product_code}</div>
            <div class="metrics">
                <div class="metric"><span class="label">Planned</span><b>{escape(str(machine.get("planned_qty") or 0))}</b></div>
                <div class="metric"><span class="label">Done</span><b>{escape(str(machine.get("completed_qty") or 0))}</b></div>
                <div class="metric"><span class="label">Remain</span><b>{escape(str(machine.get("remaining_qty") or 0))}</b></div>
            </div>
            <div class="label">Mould Number</div>
            <div class="value">{mould_number}</div>
            <div class="label">Material</div>
            <div class="value">{material}</div>
            <div class="label">Colour / Masterbatch</div>
            <div class="value">{colour}</div>
            <div class="label">Notes</div>
            <div class="value">{notes}</div>
            {stale_block}
        </div>
        """,
        unsafe_allow_html=True,
    )


def machine_button_list(machines: list[dict]) -> None:
    links = []
    for machine in machines:
        machine_id = str(machine.get("machine_id") or "").strip()
        if not machine_id:
            continue
        status = str(machine.get("status") or "No Plan")
        query = urlencode({"page": "machine_status", "machine_id": machine_id})
        links.append(
            f'<a class="machine-button" href="?{query}">{escape(machine_id)}<small>{escape(status)}</small></a>'
        )
    st.markdown(f'<div class="machine-button-grid">{"".join(links)}</div>', unsafe_allow_html=True)


def machine_status_page(settings: MobileCloudSettings) -> None:
    st.title("Machine Status")
    try:
        machines = load_machines(settings)
    except Exception:
        st.error("Unable to load machines from Supabase. Check network, schema migration, and anon key.")
        return
    if not machines:
        st.warning("No machine snapshot found. Please run publish_supabase_snapshot.bat on the factory computer.")
        return

    requested_machine_id = query_value("machine_id", "").strip()
    if not requested_machine_id:
        st.caption("Select a machine")
        machine_button_list(machines)
        return

    selected = [machine for machine in machines if str(machine.get("machine_id", "")).strip() == requested_machine_id]
    if not selected:
        st.error(f"Machine {requested_machine_id} was not found or is inactive.")
        machine_button_list(machines)
        return
    st.markdown('<a class="machine-button" href="?page=machine_status">Back to machines</a>', unsafe_allow_html=True)
    machine_card(selected[0])


def main() -> None:
    inject_css()
    load_cloud_environment()
    settings = load_mobile_cloud_settings()
    try:
        validate_mobile_cloud_settings(settings)
    except RuntimeError as exc:
        st.error(str(exc))
        st.info(
            "Configure SUPABASE_URL, SUPABASE_ANON_KEY, and MOBILE_PIN in the cloud platform environment."
        )
        return
    page = query_value("page", "stock_in")
    if page == "machine_status":
        machine_status_page(settings)
    else:
        if not require_pin(settings.mobile_pin):
            return
        stock_in_request_page(settings)


if __name__ == "__main__":
    main()
