from __future__ import annotations

import os
import hashlib
import json
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


CLOUD_ENV_NAMES = ("SUPABASE_URL", "SUPABASE_ANON_KEY", "MOBILE_PIN", "TECH_MANAGER_PIN", "MOULD_MANAGER_PIN", "DEBUG_SUPABASE")
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
        const upsertMeta = (name, content) => {
            let meta = doc.head.querySelector(`meta[name="${name}"]`);
            if (!meta) {
                meta = doc.createElement('meta');
                meta.setAttribute('name', name);
                doc.head.appendChild(meta);
            }
            meta.setAttribute('content', content);
        };
        upsertMeta('color-scheme', 'only light');
        upsertMeta('theme-color', '#F5F7FC');
        doc.documentElement.style.colorScheme = 'only light';
        if (doc.body) {
            doc.body.style.colorScheme = 'only light';
        }
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
        .production-notes-card {
            margin-top: 0.65rem;
            border: 1px solid #d8e3f3;
            border-radius: 10px;
            overflow: hidden;
            background: #ffffff;
        }
        .production-notes-title {
            padding: 0.5rem 0.62rem;
            font-size: 0.92rem;
            font-weight: 850;
            color: #1e3a8a;
            background: #eff6ff;
            border-bottom: 1px solid #d8e3f3;
        }
        .production-notes-table {
            width: 100%;
            border-collapse: collapse;
            table-layout: fixed;
            font-size: 0.88rem;
        }
        .production-notes-table th,
        .production-notes-table td {
            border-bottom: 1px solid #e5edf7;
            padding: 0.45rem 0.5rem;
            vertical-align: top;
            overflow-wrap: anywhere;
        }
        .production-notes-table tr:last-child th,
        .production-notes-table tr:last-child td {
            border-bottom: 0;
        }
        .production-notes-group {
            width: 25%;
            font-weight: 850;
            text-align: center;
        }
        .production-notes-field {
            width: 39%;
            font-weight: 800;
            color: #1f2937;
        }
        .production-notes-value {
            width: 36%;
            color: #111827;
            font-weight: 500;
        }
        .mould-note-cloud {
            margin-top: 0.65rem;
            border: 1px solid #d8e3f3;
            border-radius: 10px;
            background: #ffffff;
            overflow: hidden;
        }
        .mould-note-cloud summary {
            list-style: none;
            cursor: pointer;
            padding: 0.55rem 0.62rem;
            color: #1e3a8a;
            background: #eff6ff;
            font-weight: 850;
            border-bottom: 1px solid #d8e3f3;
        }
        .mould-note-cloud summary::-webkit-details-marker {
            display: none;
        }
        .mould-info-link {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            min-height: 40px;
            margin-top: 0.42rem;
            padding: 0.42rem 0.72rem;
            border: 1px solid #cbd5e1;
            border-radius: 10px;
            background: #ffffff;
            color: #1e3a8a !important;
            font-size: 0.94rem;
            font-weight: 850;
            text-decoration: none !important;
        }
        .mould-info-link:hover,
        .mould-info-link:active {
            background: #eff6ff;
            color: #1d4ed8 !important;
        }
        .mould-note-section {
            padding: 0.55rem 0.62rem;
            border-bottom: 1px solid #e5edf7;
        }
        .mould-note-section:last-child {
            border-bottom: 0;
        }
        .mould-note-section-title {
            color: #5f6878;
            font-size: 0.86rem;
            font-weight: 820;
            margin-bottom: 0.2rem;
        }
        .mould-note-section-body {
            color: #172033;
            font-size: 1rem;
            font-weight: 650;
            white-space: pre-wrap;
            overflow-wrap: anywhere;
        }
        .mould-readonly-card {
            margin: 0.62rem 0;
            border: 1px solid #d8e3f3;
            border-radius: 12px;
            background: #ffffff;
            overflow: hidden;
        }
        .mould-readonly-title {
            padding: 0.56rem 0.68rem;
            background: #eff6ff;
            color: #1e3a8a;
            font-size: 0.96rem;
            font-weight: 900;
            border-bottom: 1px solid #d8e3f3;
        }
        .mould-readonly-grid {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 0.48rem;
            padding: 0.62rem;
        }
        .mould-kv {
            min-width: 0;
            border: 1px solid #e5edf7;
            border-radius: 10px;
            background: #f8fafc;
            padding: 0.52rem;
        }
        .mould-kv-label {
            color: #5f6878;
            font-size: 0.78rem;
            font-weight: 760;
            line-height: 1.2;
        }
        .mould-kv-value {
            color: #172033;
            font-size: 1rem;
            font-weight: 880;
            margin-top: 0.18rem;
            overflow-wrap: anywhere;
        }
        .mould-stage-list {
            display: grid;
            grid-template-columns: 1fr;
            gap: 0.5rem;
            padding: 0.62rem;
        }
        .mould-stage-card {
            border: 1px solid #e5edf7;
            border-radius: 10px;
            background: #ffffff;
            padding: 0.58rem;
        }
        .mould-stage-name {
            color: #111827;
            font-size: 0.96rem;
            font-weight: 900;
            margin-bottom: 0.42rem;
        }
        .mould-note-readonly {
            margin: 0.62rem;
            padding: 0.62rem;
            border-radius: 10px;
            background: #f8fafc;
            border: 1px solid #e5edf7;
            color: #172033;
            white-space: pre-wrap;
            overflow-wrap: anywhere;
            font-weight: 650;
        }
        @media (max-width: 480px) {
            .mould-readonly-grid {
                grid-template-columns: 1fr;
            }
        }
        .notes-packaging {
            background: #dbeafe;
            color: #1d4ed8;
        }
        .notes-spec {
            background: #dcfce7;
            color: #166534;
        }
        .notes-protection {
            background: #ffedd5;
            color: #c2410c;
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
        .stock-product-field.qty-planned {
            background: #dbeafe;
            border: 1px solid #93c5fd;
        }
        .stock-product-field.qty-planned .field-value {
            color: #1d4ed8;
        }
        .stock-product-field.qty-completed {
            background: #dcfce7;
            border: 1px solid #86efac;
        }
        .stock-product-field.qty-completed .field-value {
            color: #15803d;
        }
        .stock-product-field.qty-remaining {
            background: #ffedd5;
            border: 1px solid #fdba74;
        }
        .stock-product-field.qty-remaining .field-value {
            color: #c2410c;
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
        html,
        body,
        [data-testid="stAppViewContainer"],
        [data-testid="stMain"],
        [data-testid="stHeader"],
        .stApp {
            color-scheme: only light !important;
            background-color: #F5F7FC !important;
            color: #172033 !important;
            filter: none !important;
            backdrop-filter: none !important;
        }
        [data-testid="stMain"] .block-container,
        div[data-testid="stVerticalBlock"],
        div[data-testid="stHorizontalBlock"] {
            background-color: transparent !important;
            color: #172033 !important;
        }
        h1, h2, h3, h4, h5, h6,
        p, label, legend,
        .stMarkdown,
        div[data-testid="stMarkdownContainer"],
        div[data-testid="stMarkdownContainer"] p,
        div[data-testid="stMarkdownContainer"] span,
        div[data-testid="stCaptionContainer"],
        .caption,
        .label,
        .field-label,
        .product-code,
        .machine-button small {
            color: #172033 !important;
        }
        .label,
        .field-label,
        .product-code,
        div[data-testid="stCaptionContainer"],
        .machine-button small {
            color: #5F6878 !important;
        }
        .value,
        .field-value,
        .product-title,
        .machine-id,
        .metric b,
        .production-notes-value,
        .production-notes-field {
            color: #172033 !important;
        }
        .stApp a:not(.machine-button):not(.language-link),
        div[data-testid="stMarkdownContainer"] a {
            color: #FF4B4B !important;
        }
        .public-card,
        .success-card,
        .summary-card,
        .stock-product-card,
        .production-notes-card,
        .metric,
        .stock-product-field,
        .machine-button,
        .language-link,
        details,
        div[data-testid="stExpander"],
        div[data-testid="stFileUploader"],
        section[data-testid="stFileUploader"] {
            background-color: #FFFFFF !important;
            color: #172033 !important;
            border-color: #CBD5E1 !important;
            filter: none !important;
            backdrop-filter: none !important;
        }
        .production-notes-title {
            background-color: #DCEEFF !important;
            color: #075985 !important;
            border-color: #CBD5E1 !important;
        }
        .production-notes-table,
        .production-notes-table th,
        .production-notes-table td {
            background-color: #FFFFFF !important;
            color: #172033 !important;
            border-color: #CBD5E1 !important;
        }
        .notes-packaging,
        .stock-product-field.qty-planned {
            background-color: #DCEEFF !important;
            color: #075985 !important;
            border-color: #93C5FD !important;
        }
        .notes-spec,
        .selected-flag,
        .stock-product-field.qty-completed,
        .status-badge.status-running,
        .machine-button.status-running {
            background-color: #DCFCE7 !important;
            color: #166534 !important;
            border-color: #86EFAC !important;
        }
        .notes-protection,
        .stock-product-field.qty-remaining,
        .status-badge.status-setup,
        .status-badge.status-changeover,
        .machine-button.status-setup,
        .machine-button.status-changeover {
            background-color: #FEF3C7 !important;
            color: #92400E !important;
            border-color: #FDE68A !important;
        }
        .status-badge.status-paused,
        .status-badge.status-stopped,
        .status-badge.status-finished,
        .machine-button.status-paused,
        .machine-button.status-stopped,
        .machine-button.status-finished {
            background-color: #FEE2E2 !important;
            color: #991B1B !important;
            border-color: #FECACA !important;
        }
        .status-badge.status-maintenance,
        .status-badge.status-no-plan,
        .machine-button.status-maintenance,
        .machine-button.status-no-plan {
            background-color: #DCEEFF !important;
            color: #075985 !important;
            border-color: #BAE6FD !important;
        }
        .stock-product-field.qty-planned .field-value {
            color: #075985 !important;
        }
        .stock-product-field.qty-completed .field-value {
            color: #166534 !important;
        }
        .stock-product-field.qty-remaining .field-value {
            color: #92400E !important;
        }
        input,
        textarea,
        select,
        [data-baseweb="input"],
        [data-baseweb="input"] input,
        [data-baseweb="select"],
        [data-baseweb="select"] > div,
        [data-baseweb="textarea"],
        [data-baseweb="textarea"] textarea,
        [data-baseweb="datepicker"],
        [data-baseweb="datepicker"] input,
        div[data-testid="stTextInput"] input,
        div[data-testid="stNumberInput"] input,
        div[data-testid="stTextArea"] textarea,
        div[data-testid="stSelectbox"] [data-baseweb="select"],
        div[data-testid="stMultiSelect"] [data-baseweb="select"],
        div[data-testid="stDateInput"] input,
        div[data-testid="stFileUploaderDropzone"] {
            background-color: #FFFFFF !important;
            color: #172033 !important;
            -webkit-text-fill-color: #172033 !important;
            caret-color: #172033 !important;
            border-color: #CBD5E1 !important;
            opacity: 1 !important;
            box-shadow: none !important;
        }
        input::placeholder,
        textarea::placeholder,
        [data-baseweb="input"] input::placeholder,
        [data-baseweb="textarea"] textarea::placeholder {
            color: #7C8798 !important;
            -webkit-text-fill-color: #7C8798 !important;
            opacity: 1 !important;
        }
        .stButton > button,
        div[data-testid="stFormSubmitButton"] button,
        .stDownloadButton > button,
        button,
        [role="button"] {
            min-height: 48px !important;
            background-color: #FFFFFF !important;
            color: #172033 !important;
            -webkit-text-fill-color: #172033 !important;
            border: 1px solid #CBD5E1 !important;
            border-radius: 10px !important;
            opacity: 1 !important;
            box-shadow: none !important;
            filter: none !important;
        }
        .stButton > button[kind="primary"],
        div[data-testid="stFormSubmitButton"] button[kind="primary"],
        .stDownloadButton > button[kind="primary"] {
            background-color: #FF4B4B !important;
            color: #FFFFFF !important;
            -webkit-text-fill-color: #FFFFFF !important;
            border-color: #FF4B4B !important;
        }
        .stButton > button:hover,
        div[data-testid="stFormSubmitButton"] button:hover,
        .stDownloadButton > button:hover,
        .machine-button:hover,
        .language-link:hover {
            background-color: #FFF1F1 !important;
            color: #172033 !important;
            border-color: #FF4B4B !important;
        }
        .stButton > button[kind="primary"]:hover,
        div[data-testid="stFormSubmitButton"] button[kind="primary"]:hover,
        .stDownloadButton > button[kind="primary"]:hover {
            background-color: #E63F3F !important;
            color: #FFFFFF !important;
            -webkit-text-fill-color: #FFFFFF !important;
            border-color: #E63F3F !important;
        }
        .stButton > button:active,
        div[data-testid="stFormSubmitButton"] button:active,
        .stDownloadButton > button:active,
        .machine-button:active,
        .language-link:active {
            transform: translateY(1px);
            background-color: #FFE5E5 !important;
        }
        .stButton > button:focus,
        div[data-testid="stFormSubmitButton"] button:focus,
        .stDownloadButton > button:focus,
        input:focus,
        textarea:focus,
        [data-baseweb="select"]:focus-within {
            outline: 2px solid rgba(255, 75, 75, 0.32) !important;
            outline-offset: 2px !important;
            border-color: #FF4B4B !important;
        }
        .stButton > button:disabled,
        div[data-testid="stFormSubmitButton"] button:disabled,
        .stDownloadButton > button:disabled,
        button:disabled {
            background-color: #E5E7EB !important;
            color: #7C8798 !important;
            -webkit-text-fill-color: #7C8798 !important;
            border-color: #CBD5E1 !important;
            opacity: 1 !important;
        }
        div[data-testid="stRadio"],
        div[data-testid="stCheckbox"],
        div[data-testid="stRadio"] label,
        div[data-testid="stCheckbox"] label,
        div[data-testid="stRadio"] p,
        div[data-testid="stCheckbox"] p {
            color: #172033 !important;
            -webkit-text-fill-color: #172033 !important;
        }
        div[data-testid="stRadio"] input:checked,
        div[data-testid="stCheckbox"] input:checked {
            accent-color: #FF4B4B !important;
        }
        div[data-testid="stRadio"] [aria-checked="true"],
        div[data-testid="stCheckbox"] [aria-checked="true"] {
            border-color: #FF4B4B !important;
        }
        div[data-testid="stAlert"],
        div[data-baseweb="notification"] {
            background-color: #DCEEFF !important;
            color: #075985 !important;
            border-color: #BAE6FD !important;
        }
        div[data-testid="stAlert"] p,
        div[data-testid="stAlert"] span,
        div[data-baseweb="notification"] p,
        div[data-baseweb="notification"] span {
            color: inherit !important;
        }
        div[data-testid="stAlert"][kind="success"],
        div[data-baseweb="notification"][kind="positive"],
        .success-card {
            background-color: #DCFCE7 !important;
            color: #166534 !important;
            border-color: #86EFAC !important;
        }
        div[data-testid="stAlert"][kind="warning"],
        div[data-baseweb="notification"][kind="warning"],
        .stale-warning {
            background-color: #FEF3C7 !important;
            color: #92400E !important;
            border-color: #FDE68A !important;
        }
        div[data-testid="stAlert"][kind="error"],
        div[data-baseweb="notification"][kind="negative"] {
            background-color: #FEE2E2 !important;
            color: #991B1B !important;
            border-color: #FECACA !important;
        }
        details summary,
        div[data-testid="stExpander"] details,
        div[data-testid="stExpander"] summary,
        div[data-testid="stExpander"] div {
            background-color: #FFFFFF !important;
            color: #172033 !important;
        }
        .sticky-submit {
            background: linear-gradient(180deg, rgba(245, 247, 252, 0.65), #F5F7FC 38%) !important;
        }
        .language-link.active {
            background-color: #FF4B4B !important;
            border-color: #FF4B4B !important;
            color: #FFFFFF !important;
            -webkit-text-fill-color: #FFFFFF !important;
        }
        html,
        body,
        .stApp,
        [data-testid="stAppViewContainer"],
        [data-testid="stMain"] {
            color-scheme: only light !important;
            forced-color-adjust: none !important;
        }
        input,
        input[type="text"],
        input[type="password"],
        input[type="number"],
        input[type="search"],
        textarea,
        select,
        div[data-testid="stTextInput"],
        div[data-testid="stTextInput"] > div,
        div[data-testid="stTextInput"] [data-baseweb="input"],
        div[data-testid="stTextInput"] [data-baseweb="input"] > div,
        div[data-testid="stTextInput"] input,
        div[data-testid="stNumberInput"],
        div[data-testid="stNumberInput"] > div,
        div[data-testid="stNumberInput"] [data-baseweb="input"],
        div[data-testid="stNumberInput"] [data-baseweb="input"] > div,
        div[data-testid="stNumberInput"] input,
        div[data-testid="stTextArea"],
        div[data-testid="stTextArea"] [data-baseweb="textarea"],
        div[data-testid="stTextArea"] textarea,
        [data-baseweb="input"],
        [data-baseweb="input"] > div,
        [data-baseweb="base-input"],
        [data-baseweb="base-input"] > div,
        [data-baseweb="textarea"],
        [data-baseweb="textarea"] > div,
        [data-baseweb="select"],
        [data-baseweb="select"] > div {
            color-scheme: only light !important;
            background: #FFFFFF !important;
            background-color: #FFFFFF !important;
            background-image: none !important;
            color: #172033 !important;
            -webkit-text-fill-color: #172033 !important;
            caret-color: #172033 !important;
            border-color: #CBD5E1 !important;
            box-shadow: none !important;
            filter: none !important;
            opacity: 1 !important;
            text-shadow: none !important;
            -webkit-appearance: none !important;
            appearance: none !important;
            forced-color-adjust: none !important;
        }
        div[data-testid="stTextInput"] [data-baseweb="input"] button,
        div[data-testid="stNumberInput"] [data-baseweb="input"] button,
        [data-baseweb="input"] button {
            background: transparent !important;
            background-color: transparent !important;
            border-color: transparent !important;
            box-shadow: none !important;
            filter: none !important;
            color: #5F6878 !important;
            -webkit-text-fill-color: #5F6878 !important;
            forced-color-adjust: none !important;
        }
        input:-webkit-autofill,
        input:-webkit-autofill:hover,
        input:-webkit-autofill:focus,
        input:-webkit-autofill:active,
        textarea:-webkit-autofill,
        textarea:-webkit-autofill:hover,
        textarea:-webkit-autofill:focus,
        textarea:-webkit-autofill:active {
            -webkit-box-shadow: 0 0 0 1000px #FFFFFF inset !important;
            box-shadow: 0 0 0 1000px #FFFFFF inset !important;
            -webkit-text-fill-color: #172033 !important;
            caret-color: #172033 !important;
            background-color: #FFFFFF !important;
            color: #172033 !important;
            transition: background-color 9999s ease-out 0s !important;
        }
        input::placeholder,
        textarea::placeholder,
        input[type="password"]::placeholder,
        [data-baseweb="input"] input::placeholder,
        [data-baseweb="textarea"] textarea::placeholder {
            color: #7C8798 !important;
            -webkit-text-fill-color: #7C8798 !important;
            opacity: 1 !important;
        }
        .stButton > button,
        div[data-testid="stFormSubmitButton"] button,
        .stDownloadButton > button,
        button[data-testid="baseButton-secondary"],
        button[data-testid="baseButton-primary"],
        button[kind],
        button[kind="secondary"],
        button[kind="primary"],
        button[kind*="primary"] {
            color-scheme: only light !important;
            min-height: 48px !important;
            background-color: #FFFFFF !important;
            background-image: none !important;
            color: #172033 !important;
            -webkit-text-fill-color: #172033 !important;
            border: 1px solid #CBD5E1 !important;
            border-radius: 10px !important;
            box-shadow: none !important;
            filter: none !important;
            opacity: 1 !important;
            forced-color-adjust: none !important;
        }
        .stButton > button p,
        .stButton > button span,
        div[data-testid="stFormSubmitButton"] button p,
        div[data-testid="stFormSubmitButton"] button span,
        .stDownloadButton > button p,
        .stDownloadButton > button span,
        button[data-testid="baseButton-secondary"] p,
        button[data-testid="baseButton-secondary"] span,
        button[data-testid="baseButton-primary"] p,
        button[data-testid="baseButton-primary"] span {
            color: inherit !important;
            -webkit-text-fill-color: inherit !important;
        }
        .stButton > button[kind*="primary"],
        div[data-testid="stFormSubmitButton"] button[kind*="primary"],
        .stDownloadButton > button[kind*="primary"],
        button[data-testid="baseButton-primary"],
        button[kind*="primary"] {
            background-color: #FF4B4B !important;
            color: #FFFFFF !important;
            -webkit-text-fill-color: #FFFFFF !important;
            border-color: #FF4B4B !important;
        }
        .stButton > button:active,
        .stButton > button:focus,
        div[data-testid="stFormSubmitButton"] button:active,
        div[data-testid="stFormSubmitButton"] button:focus,
        .stDownloadButton > button:active,
        .stDownloadButton > button:focus {
            outline: 2px solid rgba(255, 75, 75, 0.32) !important;
            outline-offset: 2px !important;
            filter: none !important;
        }
        .stButton > button:disabled,
        div[data-testid="stFormSubmitButton"] button:disabled,
        .stDownloadButton > button:disabled {
            background-color: #E5E7EB !important;
            color: #7C8798 !important;
            -webkit-text-fill-color: #7C8798 !important;
            border-color: #CBD5E1 !important;
            opacity: 1 !important;
        }
        @media (prefers-color-scheme: dark) {
            html,
            body,
            [data-testid="stAppViewContainer"],
            [data-testid="stMain"],
            [data-testid="stHeader"],
            .stApp {
                color-scheme: only light !important;
                background-color: #F5F7FC !important;
                color: #172033 !important;
                filter: none !important;
                backdrop-filter: none !important;
            }
            h1, h2, h3, h4, h5, h6,
            p, label, legend,
            .stMarkdown,
            div[data-testid="stMarkdownContainer"],
            div[data-testid="stCaptionContainer"],
            .value,
            .field-value,
            .product-title,
            .machine-id,
            .metric b,
            .production-notes-value,
            .production-notes-field {
                color: #172033 !important;
                -webkit-text-fill-color: #172033 !important;
            }
            .label,
            .field-label,
            .product-code,
            .machine-button small {
                color: #5F6878 !important;
                -webkit-text-fill-color: #5F6878 !important;
            }
            .public-card,
            .success-card,
            .summary-card,
            .stock-product-card,
            .production-notes-card,
            .metric,
            .stock-product-field,
            .machine-button,
            .language-link,
            details,
            div[data-testid="stExpander"],
            input,
            textarea,
            select,
            [data-baseweb="input"],
            [data-baseweb="input"] input,
            [data-baseweb="select"],
            [data-baseweb="select"] > div,
            [data-baseweb="textarea"],
            [data-baseweb="textarea"] textarea,
            div[data-testid="stFileUploaderDropzone"] {
                background-color: #FFFFFF !important;
                color: #172033 !important;
                -webkit-text-fill-color: #172033 !important;
                border-color: #CBD5E1 !important;
                opacity: 1 !important;
                filter: none !important;
                backdrop-filter: none !important;
            }
            input::placeholder,
            textarea::placeholder {
                color: #7C8798 !important;
                -webkit-text-fill-color: #7C8798 !important;
                opacity: 1 !important;
            }
            .stButton > button,
            div[data-testid="stFormSubmitButton"] button,
            .stDownloadButton > button,
            button,
            [role="button"] {
                min-height: 48px !important;
                background-color: #FFFFFF !important;
                color: #172033 !important;
                -webkit-text-fill-color: #172033 !important;
                border-color: #CBD5E1 !important;
                opacity: 1 !important;
                filter: none !important;
            }
            .stButton > button[kind="primary"],
            div[data-testid="stFormSubmitButton"] button[kind="primary"],
            .stDownloadButton > button[kind="primary"],
            .language-link.active {
                background-color: #FF4B4B !important;
                color: #FFFFFF !important;
                -webkit-text-fill-color: #FFFFFF !important;
                border-color: #FF4B4B !important;
            }
            .status-badge.status-running,
            .machine-button.status-running,
            .stock-product-field.qty-completed,
            .success-card,
            .selected-flag {
                background-color: #DCFCE7 !important;
                color: #166534 !important;
                border-color: #86EFAC !important;
            }
            .status-badge.status-setup,
            .status-badge.status-changeover,
            .machine-button.status-setup,
            .machine-button.status-changeover,
            .stock-product-field.qty-remaining,
            .stale-warning {
                background-color: #FEF3C7 !important;
                color: #92400E !important;
                border-color: #FDE68A !important;
            }
            .status-badge.status-paused,
            .status-badge.status-stopped,
            .status-badge.status-finished,
            .machine-button.status-paused,
            .machine-button.status-stopped,
            .machine-button.status-finished {
                background-color: #FEE2E2 !important;
                color: #991B1B !important;
                border-color: #FECACA !important;
            }
            .status-badge.status-maintenance,
            .status-badge.status-no-plan,
            .machine-button.status-maintenance,
            .machine-button.status-no-plan,
            .stock-product-field.qty-planned,
            div[data-testid="stAlert"],
            div[data-baseweb="notification"] {
                background-color: #DCEEFF !important;
                color: #075985 !important;
                border-color: #BAE6FD !important;
            }
            .sticky-submit {
                background: linear-gradient(180deg, rgba(245, 247, 252, 0.65), #F5F7FC 38%) !important;
            }
        }
        @media (max-width: 360px) {
            .block-container { padding-left: 10px; padding-right: 10px; }
            .metrics, .machine-button-grid, .stock-product-grid { grid-template-columns: 1fr; }
            .production-notes-table,
            .production-notes-table tbody,
            .production-notes-table tr,
            .production-notes-table th,
            .production-notes-table td {
                display: block;
                width: 100%;
            }
            .production-notes-group {
                text-align: left;
            }
            h1 { font-size: 1.38rem !important; }
        }
        .production-notes-table th.notes-packaging,
        .production-notes-table td.notes-packaging,
        .production-notes-group.notes-packaging,
        .notes-packaging {
            background-color: #DCEEFF !important;
            color: #075985 !important;
            border-color: #93C5FD !important;
        }
        .production-notes-table th.notes-spec,
        .production-notes-table td.notes-spec,
        .production-notes-group.notes-spec,
        .notes-spec {
            background-color: #DCFCE7 !important;
            color: #166534 !important;
            border-color: #86EFAC !important;
        }
        .production-notes-table th.notes-protection,
        .production-notes-table td.notes-protection,
        .production-notes-group.notes-protection,
        .notes-protection {
            background-color: #FEF3C7 !important;
            color: #92400E !important;
            border-color: #FDE68A !important;
        }
        .production-notes-table th.notes-packaging *,
        .production-notes-table td.notes-packaging *,
        .production-notes-table th.notes-spec *,
        .production-notes-table td.notes-spec *,
        .production-notes-table th.notes-protection *,
        .production-notes-table td.notes-protection * {
            color: inherit !important;
            -webkit-text-fill-color: inherit !important;
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
    if value in {"mould", "moulds", "mould_management", "mould_manager"}:
        return "moulds" if value != "mould" else "mould"
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


def require_tech_manager_pin(settings: MobileCloudSettings) -> bool:
    if st.session_state.get("tech_manager_pin_ok"):
        return True
    tech_pin = str(getattr(settings, "tech_manager_pin", "") or "").strip()
    if not tech_pin:
        st.error("TECH_MANAGER_PIN is not configured. Add it in Streamlit Cloud secrets before enabling cloud mould management.")
        return False
    st.title("Mould Manager / 模具管理")
    with st.form("tech_manager_pin_form"):
        pin = st.text_input("Technical manager PIN / 技术经理 PIN", type="password", placeholder="Enter technical manager PIN")
        submitted = st.form_submit_button(t("common.continue"))
    if submitted:
        if pin == tech_pin:
            st.session_state["tech_manager_pin_ok"] = True
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


def load_public_mould_machine_settings(settings: MobileCloudSettings) -> list[dict]:
    client = mobile_cloud_client(settings)
    response = client.table("mobile_public_mould_machine_settings").select("*").eq("is_active", True).execute()
    return response.data or []


def mould_snapshot_lookup(moulds: list[dict]) -> dict[str, dict]:
    return {
        str(mould.get("mould_number") or "").strip().casefold(): mould
        for mould in moulds
        if str(mould.get("mould_number") or "").strip()
    }


def normalize_machine_key(value: object) -> str:
    text = str(value or "").strip().casefold()
    if text.startswith("machine "):
        text = text.replace("machine ", "", 1).strip()
    if text.endswith(".0"):
        text = text[:-2]
    return text


def mould_setting_lookup(settings_rows: list[dict]) -> dict[tuple[str, str], dict]:
    return {
        (
            str(row.get("mould_number") or "").strip().casefold(),
            normalize_machine_key(row.get("machine_id")),
        ): row
        for row in settings_rows
        if str(row.get("mould_number") or "").strip() and normalize_machine_key(row.get("machine_id"))
    }


def cloud_mould_note_block(
    mould_number: object,
    machine_id: object,
    moulds_by_number: dict[str, dict] | None = None,
    settings_by_pair: dict[tuple[str, str], dict] | None = None,
) -> str:
    mould_text = str(mould_number or "").strip()
    if not mould_text or mould_text == "-":
        return '<span class="mould-info-empty"></span>'
    query = url_with_lang("mould", mould_number=mould_text)
    return (
        f'<a class="mould-info-link" href="{escape(query)}">'
        'View mould info / 查看模具信息'
        '</a>'
    )


def reset_stock_request() -> None:
    st.session_state["stock_client_request_id"] = str(uuid4())
    st.session_state["stock_request_success"] = None
    st.session_state["stock_last_submitted_id"] = ""
    st.session_state.pop("selected_stock_product_id", None)
    st.session_state.pop("selected_stock_machine_id", None)
    st.session_state.pop("stock_machine_choice", None)
    st.session_state.pop("stock_in_draft", None)
    st.session_state["stock_step"] = "machine"


def current_request_id() -> str:
    if not st.session_state.get("stock_client_request_id"):
        reset_stock_request()
    return str(st.session_state["stock_client_request_id"])


def reset_production_change_request() -> None:
    st.session_state["production_change_client_request_id"] = str(uuid4())
    st.session_state["production_change_success"] = None


def reset_mould_change_request() -> None:
    st.session_state["mould_change_client_request_id"] = str(uuid4())
    st.session_state["mould_change_success"] = None
    st.session_state["mould_change_last_submitted_id"] = ""


def mould_change_request_id() -> str:
    if not st.session_state.get("mould_change_client_request_id"):
        reset_mould_change_request()
    return str(st.session_state["mould_change_client_request_id"])


def production_change_request_id() -> str:
    if not st.session_state.get("production_change_client_request_id"):
        reset_production_change_request()
    return str(st.session_state["production_change_client_request_id"])


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



def format_local_datetime(value: object) -> str:
    if not value:
        return "-"
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.astimezone(ZoneInfo("Australia/Perth")).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return str(value)


def submit_mould_change_request(settings: MobileCloudSettings, payload: dict[str, object]) -> bool:
    request_id = mould_change_request_id()
    if st.session_state.get("mould_change_last_submitted_id") == request_id:
        st.warning("This mould request was already submitted. It will not be duplicated.")
        return False
    payload = {**payload, "client_request_id": request_id, "source": "cloud_mobile", "status": "pending"}
    try:
        mobile_cloud_client(settings).table("mould_change_requests").insert(payload, returning=ReturnMethod.minimal).execute()
        st.session_state["mould_change_last_submitted_id"] = request_id
        st.session_state["mould_change_success"] = {
            "client_request_id": request_id,
            "request_type": payload.get("request_type", ""),
            "mould_number": payload.get("mould_number", ""),
        }
        return True
    except Exception as exc:
        if duplicate_error(exc):
            st.warning("This mould request was already received and will not be duplicated.")
            return False
        show_supabase_diagnostic("Mould request failed. Ask admin to run the mould cloud migration SQL.", exc)
        return False


def mould_value_card(label: str, value: object) -> str:
    return f'<div class="label">{escape(str(label or ""))}</div><div class="value">{escape(str(value or "-"))}</div>'


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
        (t("machine.planned"), number_display(item.get("planned_qty")), "qty-planned"),
        (t("machine.done"), number_display(item.get("completed_qty")), "qty-completed"),
        (t("stock.product_card_remaining"), number_display(remaining), "qty-remaining"),
        (t("machine.mould_number"), str(item.get("mould_number") or "-"), ""),
        (t("machine.material"), str(item.get("material") or "-"), ""),
        (t("machine.colour"), str(item.get("colour_masterbatch") or "-"), ""),
        (t("stock.full_pallet_qty"), number_display(pallet_qty) if pallet_qty else "-", ""),
    ]
    field_html = "".join(
        f'<div class="stock-product-field {css_name}"><div class="field-label">{escape(str(label))}</div>'
        f'<div class="field-value">{escape(str(value))}</div></div>'
        for label, value, css_name in fields
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


STOCK_STEPS = ("machine", "product", "quantity", "confirm")


def stock_step() -> str:
    step = str(st.session_state.get("stock_step") or "machine")
    if step not in STOCK_STEPS:
        step = "machine"
    st.session_state["stock_step"] = step
    return step


def stock_key_fragment(value: object) -> str:
    raw = str(value or "item")
    safe = "".join(ch if ch.isalnum() else "_" for ch in raw)[:80]
    return safe or "item"


def stock_item_label(item: dict) -> str:
    return (
        f"{status_display(item.get('status'))} | "
        f"{item.get('product_code')} | {item.get('product_name')}"
    )


def stock_machine_ids(selectable_items: list[dict]) -> list[str]:
    return sorted(
        {str(item.get("machine_id") or "") for item in selectable_items if item.get("machine_id")},
        key=lambda machine: (
            0
            if any(
                str(i.get("machine_id") or "") == machine
                and normalized_queue_status(i.get("status")) == "Running"
                for i in selectable_items
            )
            else 1,
            machine,
        ),
    )


def stock_items_for_machine(selectable_items: list[dict], machine_id: str) -> list[dict]:
    return sorted(
        [
            item
            for item in selectable_items
            if str(item.get("machine_id") or "") == machine_id
            and stock_selectable_status(item.get("status"))
        ],
        key=stock_item_sort_key,
    )


def selected_stock_item(machine_items: list[dict]) -> dict | None:
    selected_id = str(st.session_state.get("selected_stock_product_id") or "")
    if not selected_id:
        return None
    return next((item for item in machine_items if stock_item_id(item) == selected_id), None)


def stock_form_keys(selected_id: str) -> tuple[str, str, str, str]:
    suffix = stock_key_fragment(selected_id)
    return (
        f"stock_mode_{suffix}",
        f"stock_qty_{suffix}",
        f"stock_operator_{suffix}",
        f"stock_note_{suffix}",
    )


def stock_form_values(selected_id: str, pallet_qty: int | None) -> tuple[str, int, str, str]:
    mode_key, qty_key, operator_key, note_key = stock_form_keys(selected_id)
    mode = str(st.session_state.get(mode_key) or "full_pallet")
    if mode not in {"full_pallet", "custom"}:
        mode = "full_pallet"
    if mode == "full_pallet":
        qty = int(pallet_qty or 0)
    else:
        qty = int(st.session_state.get(qty_key) or 0)
    operator = str(st.session_state.get(operator_key) or "").strip()
    note = str(st.session_state.get(note_key) or "")
    return mode, qty, operator, note


def stock_progress(step: str) -> None:
    labels = {
        "machine": t("stock.step_machine"),
        "product": t("stock.step_product"),
        "quantity": t("stock.step_quantity"),
        "confirm": t("stock.step_confirm"),
    }
    st.markdown(f"**{escape(labels.get(step, labels['machine']))}**")


def stock_summary_card(rows: list[tuple[str, object]]) -> None:
    html_parts = []
    for label, value in rows:
        display_value = "-" if value is None or value == "" else value
        html_parts.append(
            f'<div class="label">{escape(str(label))}</div>'
            f'<div class="value">{escape(str(display_value))}</div>'
        )
    body = "".join(html_parts)
    st.markdown(f'<div class="summary-card">{body}</div>', unsafe_allow_html=True)


def _stock_step_machine(selectable_items: list[dict]) -> None:
    stock_progress("machine")
    st.subheader(t("stock.choose_machine"))
    machine_ids = stock_machine_ids(selectable_items)
    machine_search = st.text_input(t("stock.search_machine"), key="stock_machine_search")
    if machine_search:
        machine_ids = [machine for machine in machine_ids if machine_search.casefold() in machine.casefold()]
    if not machine_ids:
        st.warning(t("stock.no_items"))
        return
    machine_id = st.selectbox(
        t("stock.machine"),
        [""] + machine_ids,
        key="stock_machine_choice",
        format_func=lambda value: t("stock.choose_machine") if not value else value,
    )
    if not machine_id:
        st.info(t("stock.choose_machine_hint"))
        return
    st.session_state["selected_stock_machine_id"] = machine_id
    st.session_state.pop("selected_stock_product_id", None)
    st.session_state["stock_step"] = "product"
    st.rerun()


def _stock_step_product(selectable_items: list[dict], products_by_code: dict[str, int]) -> None:
    stock_progress("product")
    machine_id = str(st.session_state.get("selected_stock_machine_id") or "")
    if not machine_id:
        st.warning(t("stock.no_selected_machine"))
        st.session_state["stock_step"] = "machine"
        return
    st.info(f"{t('stock.current_machine')}: {machine_id}")
    if st.button(t("stock.back_change_machine"), key="stock_back_machine"):
        st.session_state.pop("selected_stock_machine_id", None)
        st.session_state.pop("selected_stock_product_id", None)
        st.session_state.pop("stock_machine_choice", None)
        st.session_state["stock_step"] = "machine"
        st.rerun()

    machine_items_all = stock_items_for_machine(selectable_items, machine_id)
    if not machine_items_all:
        st.warning(t("stock.no_machine_products", machine_id=machine_id))
        return
    st.subheader(t("stock.select_product"))
    product_search = st.text_input(t("stock.search_product"), key=f"stock_product_search_{stock_key_fragment(machine_id)}")
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
            if st.button(
                button_label,
                key=f"stock_product_select_{stock_key_fragment(item_id)}",
                type="primary" if selected else "secondary",
            ):
                st.session_state["selected_stock_product_id"] = item_id
                st.session_state["selected_stock_machine_id"] = machine_id
                st.session_state["stock_step"] = "quantity"
                st.rerun()


def _stock_step_quantity(selectable_items: list[dict], products_by_code: dict[str, int]) -> None:
    stock_progress("quantity")
    machine_id = str(st.session_state.get("selected_stock_machine_id") or "")
    machine_items = stock_items_for_machine(selectable_items, machine_id)
    selected_product = selected_stock_item(machine_items)
    if not machine_id:
        st.warning(t("stock.no_selected_machine"))
        st.session_state["stock_step"] = "machine"
        return
    if not selected_product:
        st.warning(t("stock.no_selected_product"))
        st.session_state["stock_step"] = "product"
        return

    selected_id = stock_item_id(selected_product)
    pallet_qty = resolved_pallet_qty(selected_product, products_by_code)
    mode_key, qty_key, operator_key, note_key = stock_form_keys(selected_id)
    if mode_key not in st.session_state:
        st.session_state[mode_key] = "full_pallet"
    if qty_key not in st.session_state:
        st.session_state[qty_key] = 1
    if operator_key not in st.session_state:
        st.session_state[operator_key] = str(st.session_state.get("stock_last_operator") or "")

    st.info(f"{t('stock.current_machine')}: {machine_id}")
    stock_summary_card(
        [
            (t("stock.confirm_product"), stock_item_label(selected_product)),
            (t("common.mould"), selected_product.get("mould_number") or "-"),
            (t("stock.full_pallet_qty"), number_display(pallet_qty) if pallet_qty else "-"),
        ]
    )
    if st.button(t("stock.back_reselect_product"), key="stock_back_product"):
        st.session_state.pop("selected_stock_product_id", None)
        st.session_state["stock_step"] = "product"
        st.rerun()

    mode = st.radio(
        t("stock.quantity_mode"),
        ["full_pallet", "custom"],
        key=mode_key,
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
        qty = st.number_input(t("stock.custom_quantity"), min_value=1, step=1, value=1, key=qty_key)
    operator_name = st.text_input(t("common.operator"), placeholder=t("common.required"), key=operator_key)
    note = st.text_area(t("common.note_optional"), key=note_key)

    if st.button(t("stock.next_confirm"), type="primary", disabled=qty <= 0):
        try:
            if not machine_id:
                raise ValueError(t("stock.no_selected_machine"))
            if not selected_product:
                raise ValueError(t("stock.no_selected_product"))
            if mode == "full_pallet" and pallet_qty is None:
                raise ValueError(t("stock.no_pallet_qty"))
            int_quantity(qty)
            if not operator_name.strip():
                raise ValueError(t("stock.operator_required"))
        except ValueError as exc:
            st.error(str(exc))
            return
        st.session_state["stock_in_draft"] = {
            "selected_id": selected_id,
            "mode": mode,
            "qty": int(qty),
            "operator_name": operator_name.strip(),
            "note": note,
        }
        st.session_state["stock_step"] = "confirm"
        st.rerun()


def _submit_stock_in_request(
    settings: MobileCloudSettings,
    selected_product: dict,
    machine_id: str,
    pallet_qty: int | None,
    mode: str,
    qty: int,
    operator_name: str,
    note: str,
) -> None:
    request_id = current_request_id()
    selected_label = stock_item_label(selected_product)
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
        st.session_state["stock_last_operator"] = operator
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
            st.session_state["stock_last_operator"] = operator_name.strip()
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


def _stock_step_confirm(settings: MobileCloudSettings, selectable_items: list[dict], products_by_code: dict[str, int]) -> None:
    stock_progress("confirm")
    machine_id = str(st.session_state.get("selected_stock_machine_id") or "")
    machine_items = stock_items_for_machine(selectable_items, machine_id)
    selected_product = selected_stock_item(machine_items)
    if not machine_id:
        st.warning(t("stock.no_selected_machine"))
        st.session_state["stock_step"] = "machine"
        return
    if not selected_product:
        st.warning(t("stock.no_selected_product"))
        st.session_state["stock_step"] = "product"
        return

    selected_id = stock_item_id(selected_product)
    pallet_qty = resolved_pallet_qty(selected_product, products_by_code)
    draft = st.session_state.get("stock_in_draft") or {}
    if draft.get("selected_id") == selected_id:
        mode = str(draft.get("mode") or "full_pallet")
        qty = int(draft.get("qty") or 0)
        operator_name = str(draft.get("operator_name") or "").strip()
        note = str(draft.get("note") or "")
    else:
        mode, qty, operator_name, note = stock_form_values(selected_id, pallet_qty)
    if mode == "full_pallet" and pallet_qty is None:
        st.error(t("stock.no_pallet_qty"))
    try:
        int_quantity(qty)
        if not operator_name:
            raise ValueError(t("stock.operator_required"))
    except ValueError as exc:
        st.error(str(exc))

    if st.button(t("stock.back_edit_quantity"), key="stock_back_quantity"):
        st.session_state["stock_step"] = "quantity"
        st.rerun()

    stock_summary_card(
        [
            (t("common.machine"), machine_id),
            (t("stock.confirm_product"), stock_item_label(selected_product)),
            (t("common.mould"), selected_product.get("mould_number") or "-"),
            (t("stock.request_type"), request_type_label(mode)),
            (t("common.quantity"), qty),
            (t("common.operator"), operator_name or t("common.required")),
            (t("common.note_optional"), note.strip() or "-"),
        ]
    )

    st.markdown('<div class="sticky-submit">', unsafe_allow_html=True)
    submitted = st.button(t("stock.submit_request"), type="primary", disabled=qty <= 0 or not operator_name)
    st.markdown("</div>", unsafe_allow_html=True)
    if not submitted:
        return
    if mode == "full_pallet" and pallet_qty is None:
        st.error(t("stock.no_pallet_qty"))
        return
    _submit_stock_in_request(settings, selected_product, machine_id, pallet_qty, mode, qty, operator_name, note)


def stock_in_request_page(settings: MobileCloudSettings) -> None:
    st.title(t("stock.title"))
    if "stock_step" not in st.session_state:
        st.session_state["stock_step"] = "machine"
    current_request_id()
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
    if not selectable_items:
        st.warning(t("stock.no_items"))
        return
    products_by_code = product_pallet_lookup(products)
    step = stock_step()
    if step == "machine":
        _stock_step_machine(selectable_items)
    elif step == "product":
        _stock_step_product(selectable_items, products_by_code)
    elif step == "quantity":
        _stock_step_quantity(selectable_items, products_by_code)
    elif step == "confirm":
        _stock_step_confirm(settings, selectable_items, products_by_code)


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


def note_pairs_from_text(notes: object) -> dict[str, str]:
    text = str(notes or "").strip()
    pairs: dict[str, str] = {}
    if not text:
        return pairs
    for part in text.split("|"):
        if ":" not in part:
            continue
        key, value = part.split(":", 1)
        clean_key = key.strip().casefold()
        clean_value = value.strip()
        if clean_key and clean_value:
            pairs[clean_key] = clean_value
    return pairs


def note_value(record: dict, parsed_notes: dict[str, str], field_names: list[str], note_names: list[str]) -> str:
    for field in field_names:
        value = str(record.get(field) or "").strip()
        if value and value.upper() not in {"NO", "N", "FALSE", "0", "NONE", "N/A", "-"}:
            return value
    for name in note_names:
        value = parsed_notes.get(name.casefold(), "").strip()
        if value and value.upper() not in {"NO", "N", "FALSE", "0", "NONE", "N/A", "-"}:
            return value
    return ""


def mobile_production_notes_table(record: dict) -> str:
    parsed = note_pairs_from_text(record.get("notes"))
    pallet_qty = note_value(
        record,
        parsed,
        ["pallet_qty", "PalletQty", "palletQty"],
        ["Pallet Qty", "PalletQty", "pallet_qty"],
    )
    sections = [
        (
            t("machine.notes_group_packaging")
            if t("machine.notes_group_packaging") != "machine.notes_group_packaging"
            else "Packaging / 包装方式",
            "notes-packaging",
            [
                ("Packaging Type (Type)", note_value(record, parsed, ["packaging_type", "PackagingType"], ["Packaging Type", "Type"])),
                ("Packaging (Packaging)", note_value(record, parsed, ["packaging_unit", "PackagingUnit"], ["Packaging", "Packaging Unit"])),
            ],
        ),
        (
            t("machine.notes_group_spec")
            if t("machine.notes_group_spec") != "machine.notes_group_spec"
            else "Pack Spec / 包装规格",
            "notes-spec",
            [
                ("Carton/Unit/Stack", note_value(record, parsed, ["carton_unit_stack_qty", "CartonUnitStackQty"], ["Carton/Unit/Stack", "Carton Qty / Unit / Stack"])),
                ("Pallet Qty", pallet_qty),
                ("Pallet Bag", note_value(record, parsed, ["pallet_bag", "PalletBag"], ["Pallet Bag"])),
                ("Pallet Type", note_value(record, parsed, ["pallet_type", "PalletType"], ["Pallet Type"])),
            ],
        ),
        (
            t("machine.notes_group_protection")
            if t("machine.notes_group_protection") != "machine.notes_group_protection"
            else "Protection / 保护与包装",
            "notes-protection",
            [
                ("Wrap Pallet", note_value(record, parsed, ["wrap_pallet", "WrapPallet"], ["Wrap Pallet", "Wrap"])),
                ("Corner Protector", note_value(record, parsed, ["corner_protector", "CornerProtector"], ["Corner Protector", "Corner"])),
                ("Extra", note_value(record, parsed, ["additional_packaging", "AdditionalPackaging"], ["Additional Packaging", "Extra Pack", "Extra"])),
            ],
        ),
    ]
    rows: list[str] = []
    for group_label, group_class, pairs in sections:
        visible_pairs = [(label, value) for label, value in pairs if str(value or "").strip()]
        if not visible_pairs:
            continue
        rowspan = len(visible_pairs)
        for index, (field_label, value) in enumerate(visible_pairs):
            group_cell = (
                f'<th class="production-notes-group {group_class}" rowspan="{rowspan}">{escape(group_label)}</th>'
                if index == 0
                else ""
            )
            rows.append(
                "<tr>"
                f"{group_cell}"
                f'<td class="production-notes-field"><strong>{escape(field_label)}</strong></td>'
                f'<td class="production-notes-value">{escape(str(value))}</td>'
                "</tr>"
            )
    if not rows:
        notes = str(record.get("notes") or "").strip()
        if not notes:
            return ""
        return f'<div class="label">{escape(t("machine.notes"))}</div><div class="value">{escape(notes)}</div>'
    return (
        '<div class="production-notes-card">'
        f'<div class="production-notes-title">{escape(t("machine.notes"))}</div>'
        '<table class="production-notes-table"><tbody>'
        + "".join(rows)
        + "</tbody></table></div>"
    )


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


def machine_card(machine: dict, moulds_by_number: dict[str, dict] | None = None, settings_by_pair: dict[tuple[str, str], dict] | None = None) -> None:
    machine_id = escape(str(machine.get("machine_id") or "-"))
    product_name = escape(str(machine.get("product_name") or machine.get("running_product") or t("machine.no_plan")))
    product_code = escape(str(machine.get("product_code") or "-"))
    mould_number = escape(str(machine.get("mould_number") or "-"))
    material = escape(str(machine.get("material") or "-"))
    colour = escape(str(machine.get("colour_masterbatch") or "-"))
    status = str(machine.get("status") or "No Plan")
    visible_status = status_display(status)
    status_css = status_class(status)
    notes_block = mobile_production_notes_table(machine)
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
            {notes_block}
            {stale_block}
        </div>
        """,
        unsafe_allow_html=True,
    )


def production_item_card(item: dict, moulds_by_number: dict[str, dict] | None = None, settings_by_pair: dict[tuple[str, str], dict] | None = None) -> None:
    status = str(item.get("status") or "No Plan")
    status_css = status_class(status)
    planned = int(float(item.get("planned_qty") or 0))
    completed = int(float(item.get("completed_qty") or 0))
    remaining = max(planned - completed, 0)
    updated_at = format_updated_at(item.get("updated_at"))
    product_name = escape(str(item.get("product_name") or t("machine.no_plan")))
    product_code = escape(str(item.get("product_code") or "-"))
    mould_number = escape(str(item.get("mould_number") or "-"))
    material = escape(str(item.get("material") or "-"))
    colour = escape(str(item.get("colour_masterbatch") or "-"))
    notes_block = mobile_production_notes_table(item)
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
            <div class="label">{escape(t("machine.material"))}</div>
            <div class="value">{material}</div>
            <div class="label">{escape(t("machine.colour"))}</div>
            <div class="value">{colour}</div>
            <div class="label">{escape(t("machine.last_update"))}</div>
            <div class="value">{escape(updated_at)}</div>
            {notes_block}
        </div>
        """,
        unsafe_allow_html=True,
    )


def report_production_change_form(settings: MobileCloudSettings, machine: dict) -> None:
    st.subheader("Report Production Change / 报告生产变更")
    st.info("Mobile users only submit a request. The official production plan will not change until an admin reviews and applies it.")
    success = st.session_state.get("production_change_success")
    if success:
        st.success("生产变更已记录，等待管理员确认。")
        st.markdown(
            f"""
            <div class="success-card">
                <div class="label">Request ID</div><div class="value">{escape(str(success.get("client_request_id", "-")))}</div>
                <div class="label">Machine</div><div class="value">{escape(str(success.get("machine_no", "-")))}</div>
                <div class="label">New Product</div><div class="value">{escape(str(success.get("new_product", "-")))}</div>
                <div class="label">Status</div><div class="value">Pending Review</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if st.button("Create another change request / 继续提交另一个变更"):
            reset_production_change_request()
            st.rerun()
        return

    machine_no = str(machine.get("machine_id") or "").strip()
    old_product_code = str(machine.get("product_code") or "").strip()
    old_product_name = str(machine.get("product_name") or machine.get("running_product") or "").strip()
    old_color = str(machine.get("colour_masterbatch") or "").strip()
    old_plan_qty = int(float(machine.get("planned_qty") or 0))
    old_completed_qty = int(float(machine.get("completed_qty") or 0))
    old_remaining_qty = int(float(machine.get("remaining_qty") or max(old_plan_qty - old_completed_qty, 0)))

    st.markdown(
        f"""
        <div class="summary-card">
            <div class="label">Current machine / 当前机器</div><div class="value">{escape(machine_no)}</div>
            <div class="label">Old product / 原产品</div><div class="value">{escape(old_product_code)} - {escape(old_product_name)}</div>
            <div class="label">Old colour / 原颜色</div><div class="value">{escape(old_color or "-")}</div>
            <div class="metrics">
                <div class="metric"><span class="label">Plan</span><b>{old_plan_qty:,}</b></div>
                <div class="metric"><span class="label">Done</span><b>{old_completed_qty:,}</b></div>
                <div class="metric"><span class="label">Remain</span><b>{old_remaining_qty:,}</b></div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    try:
        products = load_products(settings)
    except Exception:
        products = []
    product_keyword = st.text_input("Search new product / 搜索新产品", key=f"change_product_search_{machine_no}")
    product_options = filter_products(products, product_keyword)[:80] if products else []
    selected_product = None
    if product_options:
        selected_index = st.selectbox(
            "New product / 新产品",
            range(len(product_options)),
            format_func=lambda idx: product_label(product_options[idx]),
            key=f"change_product_select_{machine_no}",
        )
        selected_product = product_options[int(selected_index)]
        default_new_code = str(selected_product.get("product_code") or "")
        default_new_name = str(selected_product.get("product_name") or default_new_code)
    else:
        st.warning("No product list is available. Enter product manually.")
        default_new_code = ""
        default_new_name = ""

    with st.form(f"production_change_form_{machine_no}"):
        new_product_code = st.text_input("New product code / 新产品编号", value=default_new_code)
        new_product_name = st.text_input("New product name / 新产品名称", value=default_new_name)
        new_color = st.text_input("New colour / 新颜色")
        change_time = st.text_input("Change time / 变更时间", value=now_display())
        reported_completed = st.number_input("Reported completed qty / 已完成数量", min_value=0, step=1, value=old_completed_qty)
        reported_remaining = st.number_input("Reported remaining qty / 剩余数量", min_value=0, step=1, value=old_remaining_qty)
        reason = st.text_area("Reason / 原因", placeholder="Product/color changed unexpectedly, material issue, urgent order, etc.")
        reported_by = st.text_input("Reported by / 报告人")
        note = st.text_area("Note / 备注", placeholder="Optional extra details")
        st.caption("Photo upload is not saved for production change requests yet. Ask admin to attach evidence separately if needed.")
        submitted = st.form_submit_button("Submit Change Request / 提交生产变更请求")

    if submitted:
        if not machine_no:
            st.error("Machine number is required.")
            return
        if not (new_product_code.strip() or new_product_name.strip()):
            st.error("New product is required.")
            return
        if not change_time.strip():
            st.error("Change time is required.")
            return
        if not reported_by.strip():
            st.error("Reported by is required.")
            return
        client_request_id = production_change_request_id()
        payload = {
            "client_request_id": client_request_id,
            "machine_no": machine_no,
            "old_product_code": old_product_code,
            "old_product_name": old_product_name,
            "old_color": old_color,
            "old_plan_qty": old_plan_qty,
            "old_completed_qty": old_completed_qty,
            "old_remaining_qty": old_remaining_qty,
            "new_product_code": new_product_code.strip(),
            "new_product_name": new_product_name.strip() or new_product_code.strip(),
            "new_color": new_color.strip(),
            "change_time": change_time.strip(),
            "reported_completed_qty": int(reported_completed),
            "reported_remaining_qty": int(reported_remaining),
            "reason": reason.strip(),
            "reported_by": reported_by.strip(),
            "note": note.strip(),
            "photo_url": None,
            "status": "pending",
            "review_status": "Pending Review",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        try:
            mobile_cloud_client(settings).table("production_change_requests").insert(payload).execute()
            st.session_state["production_change_success"] = {
                "client_request_id": client_request_id,
                "machine_no": machine_no,
                "new_product": payload["new_product_name"],
            }
            st.rerun()
        except Exception as exc:
            if duplicate_error(exc):
                st.warning("This production change request was already submitted. It will not be duplicated.")
            else:
                show_supabase_diagnostic("Production change request failed. Ask admin to check Supabase migration.", exc)


def _readonly_value(value: object) -> str:
    text = str(value or "").strip()
    return text if text else "-"


def _payload(value: object) -> object:
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return {}
        try:
            return json.loads(text)
        except Exception:
            return {}
    return {}


def _has_value(value: object) -> bool:
    text = str(value or "").strip()
    return text not in {"", "-", "None", "none", "nan", "NaN", "null"}


def _format_param(value: object, unit: str = "") -> str:
    if not _has_value(value):
        return "-"
    try:
        number = float(value)
        text = str(int(number)) if number.is_integer() else f"{number:g}"
    except Exception:
        text = str(value)
    return f"{text}{unit}" if unit and text != "-" else text


def _kv_html(label: str, value: object, unit: str = "") -> str:
    return (
        '<div class="mould-kv">'
        f'<div class="mould-kv-label">{escape(label)}</div>'
        f'<div class="mould-kv-value">{escape(_format_param(value, unit))}</div>'
        '</div>'
    )


def _section_html(title: str, body: str) -> str:
    if not body:
        return ""
    return (
        '<div class="mould-readonly-card">'
        f'<div class="mould-readonly-title">{escape(title)}</div>'
        f'{body}'
        '</div>'
    )


def _grid_html(items: list[tuple[str, object, str]]) -> str:
    body = "".join(_kv_html(label, value, unit) for label, value, unit in items)
    return f'<div class="mould-readonly-grid">{body}</div>'


def _stage_cards_html(title: str, rows_value: object, fields: list[tuple[str, str, str]]) -> str:
    rows = _payload(rows_value)
    if not isinstance(rows, list):
        return ""
    cards: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if not any(_has_value(row.get(key)) for _, key, _ in fields):
            continue
        stage = _format_param(row.get("stage"))
        values = "".join(_kv_html(label, row.get(key), unit) for label, key, unit in fields)
        cards.append(
            '<div class="mould-stage-card">'
            f'<div class="mould-stage-name">Stage {escape(stage)}</div>'
            f'<div class="mould-readonly-grid">{values}</div>'
            '</div>'
        )
    return _section_html(title, f'<div class="mould-stage-list">{"".join(cards)}</div>') if cards else ""


def _time_summary_html(setting_row: dict) -> str:
    times = _payload(setting_row.get("core_time_summary"))
    if not isinstance(times, dict):
        times = {}
    items = [
        ("Injection time / 注塑时间", times.get("injection_time_seconds"), " s"),
        ("Holding total / 保压总时间", times.get("holding_time_seconds"), " s"),
        ("Cooling time / 冷却时间", times.get("cooling_time_seconds"), " s"),
        ("Cycle time / 周期时间", times.get("cycle_time_seconds") or setting_row.get("cycle_time_seconds"), " s"),
    ]
    if not any(_has_value(value) for _, value, _ in items):
        return ""
    return _section_html("Core time / 核心时间", _grid_html(items))


def _temperature_html(setting_row: dict) -> str:
    temp = _payload(setting_row.get("temperature_summary"))
    if not isinstance(temp, dict):
        temp = {}
    items = [
        ("Nozzle / 射嘴", temp.get("nozzle"), " C"),
        ("Barrel 1 / 炮筒1", temp.get("barrel_1"), " C"),
        ("Barrel 2 / 炮筒2", temp.get("barrel_2"), " C"),
        ("Barrel 3 / 炮筒3", temp.get("barrel_3"), " C"),
        ("Barrel 4 / 炮筒4", temp.get("barrel_4"), " C"),
    ]
    hot_rows = _payload(setting_row.get("hot_runner_summary"))
    if isinstance(hot_rows, list):
        for row in hot_rows[:4]:
            if isinstance(row, dict):
                name = str(row.get("zone_name") or f"Zone {row.get('zone_number') or ''}").strip()
                items.append((f"Hot runner {name} / 热流道{name}", row.get("temperature"), " C"))
    if not any(_has_value(value) for _, value, _ in items):
        return ""
    return _section_html("Temperature / 温度", _grid_html(items))


def render_readonly_mould_info(
    record: dict,
    moulds_by_number: dict[str, dict] | None = None,
    settings_by_pair: dict[tuple[str, str], dict] | None = None,
) -> None:
    mould_text = str(record.get("mould_number") or "").strip()
    machine_text = str(record.get("machine_id") or "").strip()
    if not mould_text:
        return
    mould_key = mould_text.casefold()
    machine_key = normalize_machine_key(machine_text)
    mould_row = (moulds_by_number or {}).get(mould_key, {})
    setting_row = (settings_by_pair or {}).get((mould_key, machine_key), {})
    fallback_setting_row = next(
        (
            row
            for (row_mould, _row_machine), row in (settings_by_pair or {}).items()
            if row_mould == mould_key
        ),
        {},
    )
    used_fallback_setting = False
    if not setting_row and fallback_setting_row:
        setting_row = fallback_setting_row
        used_fallback_setting = True
    with st.expander(f"View mould info and core parameters / 查看模具信息和核心参数 - {mould_text}", expanded=False):
        st.caption("Read only / 只读显示")
        mould_items = [
            ("Mould Number / 模具编号", mould_text, ""),
            ("Mould Name / 模具名称", mould_row.get("mould_name") or mould_row.get("associated_products") if mould_row else "-", ""),
            ("Status / 状态", mould_row.get("computed_status") or mould_row.get("status") if mould_row else "-", ""),
            ("Location / 位置", mould_row.get("computed_location") or mould_row.get("storage_location") if mould_row else "-", ""),
        ]
        st.markdown(_section_html("Mould / 模具", _grid_html(mould_items)), unsafe_allow_html=True)
        notes = str(mould_row.get("notes") or "").strip() if mould_row else ""
        if notes:
            st.markdown(
                _section_html(
                    "Mould notes / 模具备注",
                    f'<div class="mould-note-readonly">{escape(notes)}</div>',
                ),
                unsafe_allow_html=True,
            )
        elif not mould_row:
            st.info("No mould snapshot published yet. Ask office PC to run publish-only sync. / 云端暂未发布该模具资料。")

        if setting_row:
            parameter_machine = setting_row.get("machine_id") or machine_text or "-"
            header = _grid_html(
                [
                    ("Current machine / 当前机器", machine_text or "-", ""),
                    ("Parameter machine / 参数机器", parameter_machine, ""),
                    ("Version / 版本", f"V{_readonly_value(setting_row.get('version'))}", ""),
                    ("Updated / 更新", format_updated_at(setting_row.get("updated_at")), ""),
                    ("Updated by / 更新人", setting_row.get("updated_by") or "-", ""),
                ]
            )
            st.markdown(_section_html("Machine parameter snapshot / 机器参数快照", header), unsafe_allow_html=True)
            if used_fallback_setting:
                st.warning("No exact machine match; showing the latest snapshot for this mould. / 未匹配到当前机器，先显示该模具已有参数快照。")
            setting_notes = str(setting_row.get("notes") or "").strip()
            if setting_notes:
                st.markdown(
                    _section_html(
                        "Parameter notes / 参数备注",
                        f'<div class="mould-note-readonly">{escape(setting_notes)}</div>',
                    ),
                    unsafe_allow_html=True,
                )
            param_html = (
                _time_summary_html(setting_row)
                + _stage_cards_html(
                    "Injection / 注塑",
                    setting_row.get("injection_summary"),
                    [("Pressure / 压力", "pressure", ""), ("Speed / 速度", "speed", ""), ("Position / 位置", "position", "")],
                )
                + _stage_cards_html(
                    "Holding / 保压",
                    setting_row.get("holding_summary"),
                    [("Pressure / 压力", "pressure", ""), ("Speed / 速度", "speed", ""), ("Time / 时间", "time", " s")],
                )
                + _temperature_html(setting_row)
            )
            if param_html:
                st.markdown(param_html, unsafe_allow_html=True)
            else:
                st.info("Parameter snapshot exists, but core parameter fields are empty. / 已有参数快照，但核心参数字段为空。")
        else:
            st.warning("No mould-machine parameter snapshot for this machine yet. Run publish-only sync after saving mould parameters. / 该机器暂无模具参数快照，请保存参数后运行发布同步。")

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
    moulds_by_number: dict[str, dict] = {}
    settings_by_pair: dict[tuple[str, str], dict] = {}
    try:
        moulds_by_number = mould_snapshot_lookup(load_public_moulds(settings))
        settings_by_pair = mould_setting_lookup(load_public_mould_machine_settings(settings))
    except Exception:
        moulds_by_number = {}
        settings_by_pair = {}
    st.markdown(f'<a class="machine-button" href="{escape(url_with_lang("machine_status"))}">{escape(t("machine.back"))}</a>', unsafe_allow_html=True)
    machine_card(selected[0], moulds_by_number, settings_by_pair)
    render_readonly_mould_info(selected[0], moulds_by_number, settings_by_pair)
    if query_value("production_change", "").strip() in {"1", "true", "yes"}:
        report_production_change_form(settings, selected[0])
        return
    change_url = url_with_lang("machine_status", machine_id=requested_machine_id, production_change="1")
    st.markdown(
        f'<a class="machine-button status-changeover" href="{escape(change_url)}">Report Production Change<br><small>报告生产变更</small></a>',
        unsafe_allow_html=True,
    )
    try:
        production_items = load_production_items(settings)
    except Exception:
        production_items = []
    machine_items = [
        item for item in production_items
        if str(item.get("machine_id", "")).strip() == requested_machine_id
        and stock_selectable_status(item.get("status"))
        and str(item.get("status") or "").strip().casefold() != "running"
    ]
    if machine_items:
        st.subheader(t("machine.production_items"))
        for item in machine_items:
            production_item_card(item, moulds_by_number, settings_by_pair)


def moulds_page(settings: MobileCloudSettings) -> None:
    st.title("Moulds / 模具")
    try:
        moulds = load_public_moulds(settings)
    except Exception as exc:
        show_supabase_diagnostic(t("moulds.load_error"), exc)
        return
    if not moulds:
        st.info("No mould snapshot found. Run the sync worker or publish-only sync from the factory computer.")
        return
    keyword = st.text_input("Search mould / 搜索模具", placeholder="15L, Bucket, MG-001")
    statuses = sorted({str(m.get("computed_status") or m.get("status") or "") for m in moulds if str(m.get("computed_status") or m.get("status") or "").strip()})
    all_label = t("moulds.all")
    status_filter = st.selectbox(t("common.status"), [all_label, *statuses])
    issue_only = st.checkbox(t("moulds.issues_only"))
    shown = 0
    for mould in moulds:
        search_blob = " ".join(
            str(mould.get(field) or "")
            for field in ["mould_number", "mould_name", "mould_type", "mould_size", "mould_series", "associated_products", "notes"]
        ).casefold()
        if keyword and keyword.casefold() not in search_blob:
            continue
        display_status = str(mould.get("computed_status") or mould.get("status") or "")
        if status_filter != all_label and display_status != status_filter:
            continue
        if issue_only and not str(mould.get("issue_description") or "").strip():
            continue
        shown += 1
        if shown > 50:
            st.warning("Showing first 50 results. Add more search text to narrow the list.")
            break
        number = escape(str(mould.get("mould_number") or "-"))
        name = escape(str(mould.get("mould_name") or mould.get("associated_products") or "-"))
        query = url_with_lang("mould", mould_number=mould.get("mould_number"))
        st.markdown(
            f'<div class="public-card">'
            f'<div class="machine-id">{number}</div>'
            f'<div class="product-title">{name}</div>'
            f'{mould_value_card("Status / 状态", display_status or "-")}'
            f'{mould_value_card("Location / 位置", mould.get("computed_location") or mould.get("storage_location") or "-")}'
            f'{mould_value_card("Notes / 备注", mould.get("notes") or "-")}'
            f'<a class="machine-button" href="{escape(query)}">{escape(t("moulds.details"))}</a>'
            f'</div>',
            unsafe_allow_html=True,
        )
    if shown == 0:
        st.info("No moulds match the current filter.")


def mould_detail_page(settings: MobileCloudSettings) -> None:
    number = query_value("mould_number", "")
    try:
        moulds = load_public_moulds(settings)
    except Exception as exc:
        show_supabase_diagnostic(t("moulds.load_error"), exc)
        return
    selected = next((m for m in moulds if str(m.get("mould_number")) == number), None)
    if not selected:
        st.error(t("moulds.not_found"))
        return
    st.title(f"{t('common.mould')} {number}")
    st.markdown(f'<a class="machine-button" href="{escape(url_with_lang("moulds"))}">Back to mould list / 返回模具列表</a>', unsafe_allow_html=True)

    st.markdown(
        f'<div class="public-card">'
        f'<div class="machine-id">{escape(str(selected.get("mould_number") or "-"))}</div>'
        f'{mould_value_card("Mould name / 模具名称", selected.get("mould_name") or selected.get("associated_products") or "-")}'
        f'{mould_value_card("Type / 类型", selected.get("mould_type") or "-")}'
        f'{mould_value_card("Size / 尺寸", selected.get("mould_size") or "-")}'
        f'{mould_value_card("Series / 系列", selected.get("mould_series") or "-")}'
        f'{mould_value_card("Status / 状态", selected.get("computed_status") or selected.get("status") or "-")}'
        f'{mould_value_card("Location / 位置", selected.get("computed_location") or selected.get("storage_location") or "-")}'
        f'{mould_value_card("Products / 产品", selected.get("associated_products") or "-")}'
        f'{mould_value_card("Notes / 注意事项", selected.get("notes") or "-")}'
        f'{mould_value_card("Updated / 更新时间", format_local_datetime(selected.get("updated_at")))}'
        f'</div>',
        unsafe_allow_html=True,
    )

    success = st.session_state.get("mould_change_success")
    if success:
        st.success(
            f"Mould request submitted. ID: {success.get('client_request_id')}. "
            "Pending - waiting for factory computer sync."
        )
        if st.button("Create another mould request / 继续提交模具请求"):
            reset_mould_change_request()
            st.rerun()
        return

    st.subheader("Technical manager actions / 技术经理操作")
    action = st.radio(
        "Action / 操作",
        ["Update notes / 修改备注", "Add maintenance record / 新增维修记录", "Mark maintenance completed / 标记维修完成"],
    )
    submitted_by = st.text_input("Submitted by / 提交人", placeholder="Technical manager name")
    if action.startswith("Update notes"):
        with st.form("mould_update_notes_form"):
            note = st.text_area("Mould notes / 模具注意事项", value=str(selected.get("notes") or ""), height=140)
            submit = st.form_submit_button("Submit note update / 提交备注修改")
        if submit:
            if not submitted_by.strip():
                st.error("Submitted by is required.")
                return
            if submit_mould_change_request(
                settings,
                {
                    "request_type": "update_notes",
                    "mould_number": number,
                    "note": note.strip(),
                    "submitted_by": submitted_by.strip(),
                },
            ):
                st.rerun()
    elif action.startswith("Add maintenance"):
        with st.form("mould_add_maintenance_form"):
            technician = st.text_input("Technician name / 维修人员", value=submitted_by)
            content = st.text_area("Maintenance content / 维修内容", height=150)
            set_maintenance = st.checkbox("Set mould to maintenance / 将模具标记为维修中", value=True)
            submit = st.form_submit_button("Submit maintenance / 提交维修记录")
        if submit:
            if not submitted_by.strip() or not technician.strip() or not content.strip():
                st.error("Submitted by, technician, and maintenance content are required.")
                return
            if submit_mould_change_request(
                settings,
                {
                    "request_type": "add_maintenance",
                    "mould_number": number,
                    "technician_name": technician.strip(),
                    "maintenance_content": content.strip(),
                    "set_maintenance": set_maintenance,
                    "submitted_by": submitted_by.strip(),
                },
            ):
                st.rerun()
    else:
        with st.form("mould_complete_maintenance_form"):
            note = st.text_area("Completion note / 完成备注", height=120)
            submit = st.form_submit_button("Submit completion / 提交维修完成")
        if submit:
            if not submitted_by.strip():
                st.error("Submitted by is required.")
                return
            if submit_mould_change_request(
                settings,
                {
                    "request_type": "complete_maintenance",
                    "mould_number": number,
                    "note": note.strip(),
                    "submitted_by": submitted_by.strip(),
                },
            ):
                st.rerun()

    st.info("Cloud mould changes are requests. The factory computer sync worker applies them to Excel, then republishes the mould snapshot.")

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
        if require_tech_manager_pin(settings):
            moulds_page(settings)
    elif page == "mould":
        if require_tech_manager_pin(settings):
            mould_detail_page(settings)
    else:
        if not require_pin(settings.mobile_pin):
            return
        stock_in_request_page(settings)


if __name__ == "__main__":
    main()
