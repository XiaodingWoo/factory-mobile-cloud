from __future__ import annotations

import os
import hashlib
from datetime import datetime, timezone
from html import escape
from urllib.parse import urlencode
from uuid import uuid4
from zoneinfo import ZoneInfo

import streamlit as st
import streamlit.components.v1 as components
from postgrest.types import ReturnMethod

from mobile_cloud_config import (
    MobileCloudSettings,
    load_mobile_cloud_settings,
    mobile_cloud_client,
    validate_mobile_cloud_settings,
)
import i18n as _i18n
try:
    from ui_theme import inject_shared_theme
except ModuleNotFoundError:
    def inject_shared_theme(mobile: bool = False) -> None:
        return None

t = _i18n.t


def current_lang(default: str = "en") -> str:
    if hasattr(_i18n, "current_lang"):
        return _i18n.current_lang(default)
    translations = getattr(_i18n, "TRANSLATIONS", {"en": {}})
    try:
        query_lang = str(st.query_params.get("lang", "") or "").strip()
    except Exception:
        query_lang = ""
    if query_lang in translations:
        st.session_state["language"] = query_lang
        return query_lang
    session_lang = str(st.session_state.get("language", "")).strip()
    if session_lang in translations:
        return session_lang
    st.session_state["language"] = default
    return default


st.set_page_config(
    page_title="Factory Mobile Cloud",
    layout="centered",
    initial_sidebar_state="collapsed",
)


CLOUD_ENV_NAMES = ("SUPABASE_URL", "SUPABASE_ANON_KEY", "MOBILE_PIN", "DEBUG_SUPABASE")
MACHINE_REQUIRED_COLUMNS = [
    "machine_id",
    "machine_name",
    "running_product",
    "product_code",
    "product_name",
    "planned_qty",
    "completed_qty",
    "remaining_qty",
    "status",
    "mould_number",
    "material",
    "material_location",
    "colour_masterbatch",
    "operator_name",
    "pallet_qty",
    "notes",
    "updated_at",
    "is_active",
]


class SupabaseMachineSchemaError(RuntimeError):
    def __init__(self, missing_columns: list[str]) -> None:
        self.missing_columns = missing_columns
        super().__init__(
            "Supabase table mobile_public_machines is missing columns: "
            + ", ".join(missing_columns)
        )


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


def debug_supabase_enabled() -> bool:
    value = os.getenv("DEBUG_SUPABASE", "").strip().lower()
    if not value:
        try:
            value = str(st.secrets.get("DEBUG_SUPABASE", "") or "").strip().lower()
        except Exception:
            value = ""
    return value in {"1", "true", "yes", "y", "on"}


def show_supabase_diagnostic(message: str, exc: Exception) -> None:
    st.error(message)
    if debug_supabase_enabled():
        st.exception(exc)
    else:
        st.caption("Enable DEBUG_SUPABASE=1 in Streamlit secrets to show detailed Supabase error details.")


def is_missing_column_error(exc: Exception, column: str) -> bool:
    text = str(exc).casefold()
    column_text = column.casefold()
    missing_markers = [
        "could not find",
        "schema cache",
        "does not exist",
        "unknown column",
        "column",
    ]
    return column_text in text and any(marker in text for marker in missing_markers)


@st.cache_data(ttl=300)
def check_supabase_machine_schema(settings: MobileCloudSettings) -> None:
    client = mobile_cloud_client(settings)
    missing: list[str] = []
    for column in MACHINE_REQUIRED_COLUMNS:
        try:
            client.table("mobile_public_machines").select(column).limit(1).execute()
        except Exception as exc:
            if is_missing_column_error(exc, column):
                missing.append(column)
                continue
            raise
    if missing:
        raise SupabaseMachineSchemaError(missing)


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
        .stock-product-card {
            background: #ffffff;
            border: 2px solid #d9dee7;
            border-radius: 12px;
            padding: 0.85rem;
            margin: 0.75rem 0 0.35rem;
            box-shadow: 0 1px 2px rgba(15, 23, 42, 0.05);
            overflow-wrap: anywhere;
        }
        .stock-product-card.selected {
            border-color: #16a34a;
            box-shadow: 0 0 0 3px rgba(22, 163, 74, 0.16);
        }
        .stock-product-card .product-title {
            font-size: 1.04rem;
            font-weight: 850;
            line-height: 1.24;
            color: #111827;
            margin-top: 0.42rem;
        }
        .stock-product-card .product-code {
            color: #4b5563;
            font-size: 0.92rem;
            font-weight: 750;
            margin-top: 0.2rem;
        }
        .stock-product-card .selected-flag {
            display: inline-flex;
            align-items: center;
            min-height: 28px;
            padding: 0.18rem 0.52rem;
            border-radius: 999px;
            background: #dcfce7;
            color: #166534;
            font-size: 0.84rem;
            font-weight: 850;
        }
        .stock-product-grid {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 0.45rem;
            margin-top: 0.65rem;
        }
        .stock-product-field {
            min-width: 0;
            border: 1px solid #e5e7eb;
            border-radius: 8px;
            padding: 0.48rem;
            background: #f8fafc;
        }
        .stock-product-field .field-label {
            color: #6b7280;
            font-size: 0.78rem;
            font-weight: 700;
        }
        .stock-product-field .field-value {
            color: #111827;
            font-size: 0.95rem;
            font-weight: 850;
            margin-top: 0.15rem;
            overflow-wrap: anywhere;
        }
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
        .machine-button.status-running {
            background: #dcfce7;
            border-color: #86efac;
            color: #166534;
        }
        .machine-button.status-paused,
        .machine-button.status-stopped,
        .machine-button.status-finished {
            background: #fee2e2;
            border-color: #fecaca;
            color: #991b1b;
        }
        .machine-button.status-setup,
        .machine-button.status-changeover {
            background: #dbeafe;
            border-color: #93c5fd;
            color: #1e40af;
        }
        .machine-button.status-maintenance,
        .machine-button.status-no-plan {
            background: #f1f5f9;
            border-color: #cbd5e1;
            color: #475569;
        }
        .machine-button.status-running small,
        .machine-button.status-paused small,
        .machine-button.status-stopped small,
        .machine-button.status-finished small,
        .machine-button.status-setup small,
        .machine-button.status-changeover small,
        .machine-button.status-maintenance small,
        .machine-button.status-no-plan small {
            color: inherit;
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
        .language-link-bar {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 0.5rem;
            margin: 0 0 0.75rem;
        }
        .language-link {
            display: flex;
            align-items: center;
            justify-content: center;
            min-height: 44px;
            padding: 0.55rem 0.5rem;
            border-radius: 10px;
            border: 1px solid #d9dee7;
            background: #ffffff;
            color: #374151;
            font-size: 1rem;
            font-weight: 800;
            text-decoration: none;
        }
        .language-link.active {
            background: #2563eb;
            border-color: #2563eb;
            color: #ffffff;
        }
        @media (max-width: 360px) {
            .block-container { padding-left: 10px; padding-right: 10px; }
            .metrics, .machine-button-grid, .stock-product-grid { grid-template-columns: 1fr; }
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


def normalize_mobile_page(page: str) -> str:
    value = str(page or "").strip().casefold()
    if value in {"machine", "machines", "machine_status"}:
        return "machine_status"
    if value in {"stock", "stock_in", "stock-in"}:
        return "stock_in"
    return str(page or "stock_in").strip() or "stock_in"


def url_with_lang(page: str, **params: object) -> str:
    payload = {"page": normalize_mobile_page(page), "lang": current_lang()}
    for key, value in params.items():
        if value is not None and str(value) != "":
            payload[key] = value
    return f"?{urlencode(payload)}"


def current_query_payload() -> dict[str, str]:
    payload: dict[str, str] = {}
    try:
        items = st.query_params.items()
    except Exception:
        items = []
    for key, value in items:
        if isinstance(value, list):
            value = value[0] if value else ""
        text = str(value or "").strip()
        if text:
            payload[str(key)] = text
    payload["page"] = normalize_mobile_page(payload.get("page", query_value("page", "stock_in")))
    return payload


def language_url(lang: str) -> str:
    payload = current_query_payload()
    payload["lang"] = lang
    return f"?{urlencode(payload)}"


def mobile_language_bar() -> None:
    current = current_lang()
    en_active = " active" if current == "en" else ""
    zh_active = " active" if current == "zh-CN" else ""
    st.markdown(
        f"""
        <div class="language-link-bar">
            <a class="language-link{en_active}" href="{escape(language_url("en"))}">English</a>
            <a class="language-link{zh_active}" href="{escape(language_url("zh-CN"))}">中文</a>
        </div>
        """,
        unsafe_allow_html=True,
    )


def require_pin(mobile_pin: str) -> bool:
    if st.session_state.get("mobile_pin_ok"):
        return True
    st.title("Factory Mobile")
    with st.form("pin_form"):
        pin = st.text_input(t("common.pin"), type="password", placeholder=t("pin.placeholder"))
        submitted = st.form_submit_button(t("common.continue"))
    if submitted:
        if pin == mobile_pin:
            st.session_state["mobile_pin_ok"] = True
            st.rerun()
        else:
            st.error(t("pin.incorrect"))
    return False


@st.cache_data(ttl=60)
def load_products(settings: MobileCloudSettings) -> list[dict]:
    client = mobile_cloud_client(settings)
    response = (
        client.table("mobile_public_products")
        .select("product_code,product_name,label,pallet_qty,search_text,is_active")
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
        .select(",".join(MACHINE_REQUIRED_COLUMNS))
        .eq("is_active", True)
        .order("machine_id")
        .execute()
    )
    return response.data or []


@st.cache_data(ttl=30)
def load_production_items(settings: MobileCloudSettings) -> list[dict]:
    client = mobile_cloud_client(settings)
    response = (
        client.table("mobile_public_production_items")
        .select(
            "schedule_id,machine_id,machine_name,sequence,status,product_code,product_name,"
            "mould_number,material,material_location,colour_masterbatch,operator_name,notes,"
            "planned_qty,completed_qty,pallet_qty,updated_at,is_active"
        )
        .eq("is_active", True)
        .in_("status", ["Running", "Next", "Queued", "Planned"])
        .order("machine_id")
        .order("sequence")
        .execute()
    )
    return response.data or []


@st.cache_data(ttl=60)
def load_public_moulds(settings: MobileCloudSettings) -> list[dict]:
    client = mobile_cloud_client(settings)
    response = client.table("mobile_public_moulds").select("*").eq("is_active", True).order("mould_number").execute()
    return response.data or []


def reset_stock_request() -> None:
    st.session_state["stock_client_request_id"] = str(uuid4())
    st.session_state["stock_request_success"] = None
    st.session_state["stock_last_submitted_id"] = ""
    st.session_state.pop("selected_stock_product_id", None)
    st.session_state.pop("selected_stock_machine_id", None)


def current_request_id() -> str:
    if not st.session_state.get("stock_client_request_id"):
        reset_stock_request()
    return str(st.session_state["stock_client_request_id"])


def int_quantity(value: object) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(t("stock.custom")) from exc
    if number <= 0:
        raise ValueError(t("stock.pallet_missing"))
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
            <div class="value">{escape(t("stock.pending"))}</div>
            <div class="label">{escape(t("common.request_id"))}</div>
            <div class="value">{escape(summary.get("request_id", ""))}</div>
            <div class="label">{escape(t("common.product"))}</div>
            <div class="value">{escape(summary.get("product", ""))}</div>
            <div class="label">{escape(t("common.quantity"))}</div>
            <div class="value">{escape(str(summary.get("quantity", "")))}</div>
            <div class="label">{escape(t("stock.request_type"))}</div>
            <div class="value">{escape(str(summary.get("request_type", "")))}</div>
            <div class="label">{escape(t("common.operator"))}</div>
            <div class="value">{escape(summary.get("operator", ""))}</div>
            <div class="label">{escape(t("common.submitted_at"))}</div>
            <div class="value">{escape(summary.get("submitted_at", ""))}</div>
            <div class="label">{escape(t("common.status"))}</div>
            <div class="value">{escape(summary.get("status", "pending"))}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def valid_pallet_qty(value: object) -> int | None:
    try:
        qty = int(float(value))
    except (TypeError, ValueError):
        return None
    return qty if qty > 0 else None


def normalized_queue_status(status: object) -> str:
    text = str(status or "").strip()
    return "Next" if text.casefold() == "queued" else text


def stock_selectable_status(status: object) -> bool:
    return normalized_queue_status(status) in {"Running", "Next", "Planned"}


def number_display(value: object) -> str:
    try:
        number = float(value or 0)
    except (TypeError, ValueError):
        return "-"
    if number.is_integer():
        return f"{int(number):,}"
    return f"{number:,.2f}"


def item_remaining_qty(item: dict) -> float:
    try:
        planned = float(item.get("planned_qty") or 0)
    except (TypeError, ValueError):
        planned = 0
    try:
        completed = float(item.get("completed_qty") or 0)
    except (TypeError, ValueError):
        completed = 0
    if item.get("remaining_qty") not in {None, ""}:
        try:
            return max(float(item.get("remaining_qty") or 0), 0)
        except (TypeError, ValueError):
            pass
    return max(planned - completed, 0)


def stock_item_id(item: dict) -> str:
    schedule_id = str(item.get("schedule_id") or "").strip()
    if schedule_id:
        return schedule_id
    return "|".join(
        str(item.get(field) or "").strip()
        for field in ["machine_id", "status", "product_code", "product_name", "mould_number"]
    )


def stock_item_sort_key(item: dict) -> tuple[int, int, str]:
    status = normalized_queue_status(item.get("status"))
    status_order = {"Running": 0, "Next": 1, "Planned": 2}.get(status, 3)
    try:
        sequence = int(float(item.get("sequence") or 999999))
    except (TypeError, ValueError):
        sequence = 999999
    return (status_order, sequence, str(item.get("product_name") or item.get("product_code") or ""))


def product_pallet_lookup(products: list[dict]) -> dict[str, int]:
    lookup: dict[str, int] = {}
    for product in products:
        code = str(product.get("product_code") or "").strip()
        qty = valid_pallet_qty(product.get("pallet_qty"))
        if code and qty:
            lookup[code.casefold()] = qty
    return lookup


def resolved_pallet_qty(item: dict, products_by_code: dict[str, int]) -> int | None:
    code = str(item.get("product_code") or "").strip().casefold()
    if code and code in products_by_code:
        return products_by_code[code]
    return valid_pallet_qty(item.get("pallet_qty"))


def request_type_label(mode: str) -> str:
    return {
        "full_pallet": t("stock.full_pallet"),
        "custom": t("stock.custom_quantity"),
    }.get(mode, mode)


def stock_product_card(item: dict, selected: bool, pallet_qty: int | None) -> None:
    status = normalized_queue_status(item.get("status"))
    css_class = status_class(status)
    remaining = item_remaining_qty(item)
    selected_flag = f'<span class="selected-flag">{escape(t("stock.selected"))}</span>' if selected else ""
    fields = [
        (t("machine.planned"), number_display(item.get("planned_qty"))),
        (t("machine.done"), number_display(item.get("completed_qty"))),
        (t("stock.product_card_remaining"), number_display(remaining)),
        (t("machine.mould_number"), str(item.get("mould_number") or "-")),
        (t("machine.material"), str(item.get("material") or "-")),
        (t("machine.colour"), str(item.get("colour_masterbatch") or "-")),
        (t("stock.full_pallet_qty"), number_display(pallet_qty) if pallet_qty else "-"),
    ]
    field_html = "".join(
        f'<div class="stock-product-field"><div class="field-label">{escape(str(label))}</div>'
        f'<div class="field-value">{escape(str(value))}</div></div>'
        for label, value in fields
    )
    html = "".join(
        [
            f'<div class="stock-product-card {css_class}{" selected" if selected else ""}">',
            selected_flag,
            f'<div class="status-badge {css_class}">{escape(t("stock.product_card_status"))}: {escape(status_display(status))}</div>',
            f'<div class="product-title">{escape(str(item.get("product_name") or "-"))}</div>',
            f'<div class="product-code">{escape(str(item.get("product_code") or "-"))}</div>',
            f'<div class="stock-product-grid">{field_html}</div>',
            "</div>",
        ]
    )
    st.markdown(html, unsafe_allow_html=True)


def production_item_search_text(item: dict) -> str:
    return " ".join(
        str(item.get(field) or "")
        for field in ["status", "product_code", "product_name", "mould_number", "machine_id"]
    ).casefold()


def filter_production_items(items: list[dict], keyword: str) -> list[dict]:
    words = [word.casefold() for word in keyword.replace(",", " ").split() if word.strip()]
    if not words:
        return items
    return [item for item in items if all(word in production_item_search_text(item) for word in words)]


def stock_in_request_page(settings: MobileCloudSettings) -> None:
    st.title(t("stock.title"))
    try:
        items = load_production_items(settings)
    except Exception as exc:
        show_supabase_diagnostic(t("stock.load_error"), exc)
        return
    try:
        products = load_products(settings)
    except Exception:
        products = []
    if not items:
        st.warning(t("stock.no_items"))
        return

    success_summary = st.session_state.get("stock_request_success")
    if success_summary:
        show_success_card(success_summary)
        if st.button(t("stock.create_another")):
            reset_stock_request()
            st.rerun()
        return

    selectable_items = [item for item in items if stock_selectable_status(item.get("status"))]
    machine_ids = sorted(
        {str(item.get("machine_id") or "") for item in selectable_items if item.get("machine_id")},
        key=lambda machine: (
            0 if any(i.get("machine_id") == machine and normalized_queue_status(i.get("status")) == "Running" for i in selectable_items) else 1,
            machine,
        ),
    )
    st.subheader(t("stock.choose_machine"))
    machine_search = st.text_input(t("stock.search_machine"))
    if machine_search:
        machine_ids = [machine for machine in machine_ids if machine_search.casefold() in machine.casefold()]
    if not machine_ids:
        st.warning(t("stock.no_items"))
        return
    machine_options = [""] + machine_ids
    machine_id = st.selectbox(
        t("stock.machine"),
        machine_options,
        format_func=lambda value: t("stock.choose_machine") if not value else value,
    )
    if not machine_id:
        st.info(t("stock.choose_machine_hint"))
        return
    if st.session_state.get("selected_stock_machine_id") != machine_id:
        st.session_state["selected_stock_machine_id"] = machine_id
        st.session_state.pop("selected_stock_product_id", None)

    products_by_code = product_pallet_lookup(products)
    machine_items_all = [
        item
        for item in selectable_items
        if str(item.get("machine_id")) == machine_id and stock_selectable_status(item.get("status"))
    ]
    machine_items_all = sorted(machine_items_all, key=stock_item_sort_key)
    if not machine_items_all:
        st.warning(t("stock.no_machine_products", machine_id=machine_id))
        return
    st.subheader(t("stock.select_product"))
    product_search = st.text_input(t("stock.search_product"))
    machine_items = filter_production_items(machine_items_all, product_search)
    if not machine_items:
        st.warning(t("stock.no_machine_products", machine_id=machine_id))
        return

    selected_id = str(st.session_state.get("selected_stock_product_id") or "")
    for section_title, section_items in [
        (t("stock.running_products"), [item for item in machine_items if normalized_queue_status(item.get("status")) == "Running"]),
        (t("stock.queued_products"), [item for item in machine_items if normalized_queue_status(item.get("status")) != "Running"]),
    ]:
        if not section_items:
            continue
        st.markdown(f"**{escape(section_title)}**")
        for item in section_items:
            item_id = stock_item_id(item)
            pallet_for_card = resolved_pallet_qty(item, products_by_code)
            selected = item_id == selected_id
            stock_product_card(item, selected, pallet_for_card)
            button_label = t("stock.selected") if selected else t("stock.select_product")
            if st.button(button_label, key=f"stock_product_select_{item_id}", type="primary" if selected else "secondary"):
                st.session_state["selected_stock_product_id"] = item_id
                st.session_state["selected_stock_machine_id"] = machine_id
                st.rerun()

    selected_product = next((item for item in machine_items_all if stock_item_id(item) == selected_id), None)
    if not selected_product:
        st.info(t("stock.select_product"))
        return

    selected_label = (
        f"{status_display(selected_product.get('status'))} | "
        f"{selected_product.get('product_code')} | {selected_product.get('product_name')}"
    )
    pallet_qty = resolved_pallet_qty(selected_product, products_by_code)
    mode_options = ["full_pallet", "custom"]
    mode = st.radio(
        t("stock.request_type"),
        mode_options,
        format_func=lambda value: {
            "full_pallet": t("stock.full_pallet"),
            "custom": t("stock.custom_quantity"),
        }.get(value, value),
    )
    if mode == "full_pallet":
        if pallet_qty is None:
            st.error(t("stock.no_pallet_qty"))
            qty = 0
        else:
            st.info(f"{t('stock.full_pallet_qty')}: {pallet_qty:,}")
            qty = pallet_qty
    else:
        qty = st.number_input(t("stock.custom_quantity"), min_value=1, step=1, value=1)
    operator_name = st.text_input(t("common.operator"), placeholder=t("common.required"))
    note = st.text_area(t("common.note_optional"))

    request_id = current_request_id()
    summary_note = note.strip() or "-"
    st.markdown(
        f"""
        <div class="summary-card">
            <div class="label">{escape(t("stock.confirm_product"))}</div>
            <div class="value">{escape(selected_label)}</div>
            <div class="label">{escape(t("common.machine"))}</div><div class="value">{escape(machine_id)}</div>
            <div class="label">{escape(t("common.mould"))}</div><div class="value">{escape(str(selected_product.get("mould_number") or "-"))}</div>
            <div class="label">{escape(t("stock.request_type"))}</div><div class="value">{escape(request_type_label(mode))}</div>
            <div class="label">{escape(t("common.quantity"))}</div>
            <div class="value">{escape(str(qty))}</div>
            <div class="label">{escape(t("common.operator"))}</div>
            <div class="value">{escape(operator_name.strip() or t("common.required"))}</div>
            <div class="label">{escape(t("common.note_optional"))}</div>
            <div class="value">{escape(summary_note)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown('<div class="sticky-submit">', unsafe_allow_html=True)
    submitted = st.button(t("stock.submit_request"), type="primary", disabled=qty <= 0)
    st.markdown("</div>", unsafe_allow_html=True)

    if not submitted:
        return
    if st.session_state.get("stock_last_submitted_id") == request_id:
        st.warning(t("stock.duplicate"))
        return

    try:
        quantity = int_quantity(qty)
        operator = operator_name.strip()
        if not operator:
            raise ValueError(t("stock.operator_required"))

        st.session_state["stock_last_submitted_id"] = request_id
        client = mobile_cloud_client(settings)
        product_code = str(selected_product.get("product_code") or "").strip()
        product_name = str(selected_product.get("product_name") or "").strip()
        client.table("stock_in_requests").insert(
            {
                "client_request_id": request_id,
                "product_code": product_code or None,
                "product_name": product_name,
                "machine_id": machine_id,
                "schedule_id": selected_product.get("schedule_id"),
                "mould_number": selected_product.get("mould_number"),
                "production_status": normalized_queue_status(selected_product.get("status")),
                "pallet_qty": pallet_qty,
                "quantity_mode": mode,
                "request_type": "stock_in",
                "loose_status": None,
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
            "request_type": request_type_label(mode),
            "operator": operator,
            "submitted_at": now_display(),
            "status": "pending",
        }
        st.rerun()
    except ValueError as exc:
        st.session_state["stock_last_submitted_id"] = ""
        st.error(str(exc))
    except Exception as exc:
        if duplicate_error(exc):
            st.warning(t("stock.received"))
            st.session_state["stock_request_success"] = {
                "request_id": request_id,
                "product": selected_label,
                "quantity": qty,
                "request_type": request_type_label(mode),
                "operator": operator_name.strip(),
                "submitted_at": now_display(),
                "status": "pending",
            }
            st.rerun()
            return
        st.session_state["stock_last_submitted_id"] = ""
        st.error(t("stock.failed"))


def status_class(status: object) -> str:
    text = str(status or "").strip().casefold()
    if "pause" in text:
        return "status-paused"
    if "stop" in text:
        return "status-stopped"
    if "finish" in text or "complete" in text:
        return "status-finished"
    if "running" in text:
        return "status-running"
    if text in {"next", "queued"}:
        return "status-setup"
    if "setup" in text:
        return "status-setup"
    if "change" in text:
        return "status-changeover"
    if "maintenance" in text:
        return "status-maintenance"
    return "status-no-plan"


def status_display(status: object) -> str:
    raw = str(status or "").strip()
    key = f"status.{raw}"
    translated = t(key)
    return (raw or t("machine.no_plan")) if translated == key else translated


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


def factory_timezone() -> ZoneInfo:
    timezone_name = os.getenv("FACTORY_TIMEZONE", "Australia/Perth").strip() or "Australia/Perth"
    try:
        return ZoneInfo(timezone_name)
    except Exception:
        return ZoneInfo("UTC")


def format_updated_at(value: object) -> str:
    parsed = parse_updated_at(value)
    if parsed is None:
        return "-"
    return parsed.astimezone(factory_timezone()).strftime("%Y-%m-%d %H:%M:%S")


def stale_minutes(updated_at: object) -> int | None:
    parsed = parse_updated_at(updated_at)
    if parsed is None:
        return None
    return int((datetime.now(timezone.utc) - parsed).total_seconds() // 60)


def machine_card(machine: dict) -> None:
    machine_id = escape(str(machine.get("machine_id") or "-"))
    product_name = escape(str(machine.get("product_name") or machine.get("running_product") or t("machine.no_plan")))
    product_code = escape(str(machine.get("product_code") or "-"))
    mould_number = escape(str(machine.get("mould_number") or "-"))
    material = escape(str(machine.get("material") or "-"))
    colour = escape(str(machine.get("colour_masterbatch") or "-"))
    status = str(machine.get("status") or "No Plan")
    visible_status = status_display(status)
    status_css = status_class(status)
    notes = escape(str(machine.get("notes") or "-"))
    raw_updated_at = machine.get("updated_at")
    updated_at = format_updated_at(raw_updated_at)
    minutes_old = stale_minutes(raw_updated_at)
    stale_block = ""
    if minutes_old is None:
        stale_block = f'<div class="stale-warning">{escape(t("machine.stale_unknown"))}</div>'
    elif minutes_old > 10:
        stale_block = f'<div class="stale-warning">{escape(t("machine.stale", minutes=minutes_old))}</div>'

    st.markdown(
        f"""
        <div class="public-card {status_css}">
            <div class="machine-title">
                <div>
                    <div class="label">{escape(t("common.machine"))}</div>
                    <div class="machine-id">{machine_id}</div>
                </div>
                <div class="status-badge {status_css}">{escape(visible_status)}</div>
            </div>
            <div class="label">{escape(t("machine.last_update"))}</div>
            <div class="value">{escape(updated_at)}</div>
            <div class="label">{escape(t("machine.product_name"))}</div>
            <div class="value">{product_name}</div>
            <div class="label">{escape(t("machine.product_code"))}</div>
            <div class="value">{product_code}</div>
            <div class="metrics">
                <div class="metric"><span class="label">{escape(t("machine.planned"))}</span><b>{escape(str(machine.get("planned_qty") or 0))}</b></div>
                <div class="metric"><span class="label">{escape(t("machine.done"))}</span><b>{escape(str(machine.get("completed_qty") or 0))}</b></div>
                <div class="metric"><span class="label">{escape(t("machine.remaining"))}</span><b>{escape(str(machine.get("remaining_qty") or 0))}</b></div>
            </div>
            <div class="label">{escape(t("machine.mould_number"))}</div>
            <div class="value">{mould_number}</div>
            <div class="label">{escape(t("machine.material"))}</div>
            <div class="value">{material}</div>
            <div class="label">{escape(t("machine.colour"))}</div>
            <div class="value">{colour}</div>
            <div class="label">{escape(t("machine.notes"))}</div>
            <div class="value">{notes}</div>
            {stale_block}
        </div>
        """,
        unsafe_allow_html=True,
    )


def production_item_card(item: dict) -> None:
    status = str(item.get("status") or "No Plan")
    status_css = status_class(status)
    planned = int(float(item.get("planned_qty") or 0))
    completed = int(float(item.get("completed_qty") or 0))
    remaining = max(planned - completed, 0)
    updated_at = format_updated_at(item.get("updated_at"))
    product_name = escape(str(item.get("product_name") or t("machine.no_plan")))
    product_code = escape(str(item.get("product_code") or "-"))
    mould_number = escape(str(item.get("mould_number") or "-"))
    st.markdown(
        f"""
        <div class="public-card {status_css}">
            <div class="machine-title">
                <div>
                    <div class="label">{escape(t("machine.product_name"))}</div>
                    <div class="value">{product_name}</div>
                </div>
                <div class="status-badge {status_css}">{escape(status_display(status))}</div>
            </div>
            <div class="label">{escape(t("machine.product_code"))}</div>
            <div class="value">{product_code}</div>
            <div class="metrics">
                <div class="metric"><span class="label">{escape(t("machine.planned"))}</span><b>{planned:,}</b></div>
                <div class="metric"><span class="label">{escape(t("machine.done"))}</span><b>{completed:,}</b></div>
                <div class="metric"><span class="label">{escape(t("machine.remaining"))}</span><b>{remaining:,}</b></div>
            </div>
            <div class="label">{escape(t("machine.mould_number"))}</div>
            <div class="value">{mould_number}</div>
            <div class="label">{escape(t("machine.last_update"))}</div>
            <div class="value">{escape(updated_at)}</div>
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
        css_class = status_class(status)
        query = url_with_lang("machine_status", machine_id=machine_id)
        links.append(
            f'<a class="machine-button {css_class}" href="{escape(query)}">{escape(machine_id)}<small>{escape(status_display(status))}</small></a>'
        )
    st.markdown(f'<div class="machine-button-grid">{"".join(links)}</div>', unsafe_allow_html=True)


def machine_status_page(settings: MobileCloudSettings) -> None:
    st.title(t("machine.title"))
    try:
        check_supabase_machine_schema(settings)
        machines = load_machines(settings)
    except SupabaseMachineSchemaError as exc:
        st.error(
            "Supabase table mobile_public_machines is missing columns: "
            + ", ".join(exc.missing_columns)
        )
        st.info("Please run supabase_migration_latest.sql in Supabase SQL Editor, then reboot this Streamlit app.")
        if debug_supabase_enabled():
            st.exception(exc)
        else:
            st.caption("Enable DEBUG_SUPABASE=1 in Streamlit secrets to show detailed Supabase error details.")
        return
    except Exception as exc:
        show_supabase_diagnostic(t("machine.load_error"), exc)
        return
    if not machines:
        st.warning(t("machine.empty"))
        return

    requested_machine_id = query_value("machine_id", "").strip()
    if not requested_machine_id:
        st.caption(t("machine.select"))
        machine_button_list(machines)
        return

    selected = [machine for machine in machines if str(machine.get("machine_id", "")).strip() == requested_machine_id]
    if not selected:
        st.error(t("machine.not_found", machine_id=requested_machine_id))
        machine_button_list(machines)
        return
    st.markdown(f'<a class="machine-button" href="{escape(url_with_lang("machine_status"))}">{escape(t("machine.back"))}</a>', unsafe_allow_html=True)
    machine_card(selected[0])
    try:
        production_items = load_production_items(settings)
    except Exception:
        production_items = []
    machine_items = [
        item for item in production_items
        if str(item.get("machine_id", "")).strip() == requested_machine_id and stock_selectable_status(item.get("status"))
    ]
    if machine_items:
        st.subheader(t("machine.production_items"))
        for item in machine_items:
            production_item_card(item)


def moulds_page(settings: MobileCloudSettings) -> None:
    st.title(t("moulds.title"))
    try:
        moulds = load_public_moulds(settings)
    except Exception:
        st.error(t("moulds.load_error"))
        return
    keyword = st.text_input(t("moulds.search"))
    all_label = t("moulds.all")
    status_filter = st.selectbox(t("common.status"), [all_label, *sorted({str(m.get("status") or "") for m in moulds})])
    issue_only = st.checkbox(t("moulds.issues_only"))
    for mould in moulds:
        if keyword and keyword.casefold() not in str(mould.get("mould_number") or "").casefold():
            continue
        if status_filter != all_label and mould.get("status") != status_filter:
            continue
        if issue_only and not str(mould.get("issue_description") or "").strip():
            continue
        number = escape(str(mould.get("mould_number") or "-"))
        query = url_with_lang("mould", mould_number=mould.get("mould_number"))
        st.markdown(
            f'<div class="public-card"><div class="machine-id">{number}</div>'
            f'<div class="label">{escape(t("common.location"))}</div><div class="value">{escape(str(mould.get("storage_location") or "-"))}</div>'
            f'<div class="label">{escape(t("common.status"))}</div><div class="value">{escape(str(mould.get("status") or "-"))}</div>'
            f'<div class="label">{escape(t("common.issue"))}</div><div class="value">{escape(str(mould.get("issue_description") or "-"))}</div>'
            f'<a href="{escape(query)}">{escape(t("moulds.details"))}</a></div>',
            unsafe_allow_html=True,
        )


def mould_detail_page(settings: MobileCloudSettings) -> None:
    number = query_value("mould_number", "")
    moulds = load_public_moulds(settings)
    selected = next((m for m in moulds if str(m.get("mould_number")) == number), None)
    if not selected:
        st.error(t("moulds.not_found"))
        return
    st.title(f"{t('common.mould')} {number}")
    for label, field in [
        (t("common.location"), "storage_location"), (t("common.status"), "status"),
        (t("common.issue"), "issue_description"), (t("common.products"), "associated_products"),
        (t("common.updated"), "updated_at"),
    ]:
        st.markdown(f"**{label}**  \n{selected.get(field) or '-'}")
    st.info(t("moulds.archive_info"))
    st.subheader(t("issue.report"))
    issue_types = ["Mould Damage", "Product Defect", "Water Line", "Air Line", "Installation", "Maintenance", "Other"]
    issue_type = st.selectbox(t("issue.type"), issue_types, format_func=lambda value: t(f"issue.{value}"))
    description = st.text_area(t("issue.description"))
    related_product = st.text_input(t("issue.related_product"))
    operator = st.text_input(t("common.operator"))
    photo = st.camera_input(t("issue.take_photo"))
    images = st.file_uploader(t("issue.upload_images"), type=["jpg", "jpeg", "png", "webp"], accept_multiple_files=True)
    video = st.file_uploader(t("issue.upload_video"), type=["mp4", "mov", "webm"])
    if st.button(t("issue.submit"), type="primary"):
        if not description.strip() or not operator.strip():
            st.error(t("issue.required"))
            return
        image_limit = int(os.getenv("MOULD_MEDIA_MAX_IMAGE_MB", "10")) * 1024 * 1024
        video_limit = int(os.getenv("MOULD_MEDIA_MAX_VIDEO_MB", "150")) * 1024 * 1024
        files = ([photo] if photo else []) + list(images or []) + ([video] if video else [])
        for file in files:
            limit = video_limit if str(file.type).startswith("video/") else image_limit
            if file.size > limit:
                st.error(t("issue.too_large", filename=file.name))
                return
        client = mobile_cloud_client(settings)
        issue_id = str(uuid4())
        request_id = str(uuid4())
        try:
            client.table("mould_issue_records").insert(
                {
                    "issue_id": issue_id, "client_request_id": request_id, "mould_number": number,
                    "related_product_code": related_product.strip() or None, "issue_type": issue_type,
                    "description": description.strip(), "status": "Open", "operator_name": operator.strip(),
                    "source": "mobile",
                },
                returning=ReturnMethod.minimal,
            ).execute()
            for file in files:
                payload = file.getvalue()
                media_id = str(uuid4())
                safe_name = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in file.name)
                storage_path = f"{number}/{issue_id}/{media_id}_{safe_name}"
                client.storage.from_("mould-issue-media-temp").upload(
                    storage_path, payload, {"content-type": file.type, "upsert": "false"}
                )
                client.table("mould_issue_media").insert(
                    {
                        "id": media_id, "client_request_id": str(uuid4()), "issue_id": issue_id,
                        "mould_number": number, "media_type": "video" if file.type.startswith("video/") else "image",
                        "storage_bucket": "mould-issue-media-temp", "storage_path": storage_path,
                        "original_filename": file.name, "mime_type": file.type, "file_size": len(payload),
                        "sha256": hashlib.sha256(payload).hexdigest(), "archive_status": "WaitingForArchive",
                        "uploaded_by": operator.strip(),
                    },
                    returning=ReturnMethod.minimal,
                ).execute()
            st.success(t("issue.success"))
        except Exception:
            st.error(t("issue.failed"))


def main() -> None:
    inject_css()
    inject_shared_theme(mobile=True)
    page = normalize_mobile_page(query_value("page", "stock_in"))
    mobile_language_bar()
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
    if page == "machine_status":
        machine_status_page(settings)
    elif page == "moulds":
        if require_pin(settings.mobile_pin):
            moulds_page(settings)
    elif page == "mould":
        if require_pin(settings.mobile_pin):
            mould_detail_page(settings)
    else:
        if not require_pin(settings.mobile_pin):
            return
        stock_in_request_page(settings)


if __name__ == "__main__":
    main()
