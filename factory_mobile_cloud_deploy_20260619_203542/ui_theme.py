from __future__ import annotations

import streamlit as st


def inject_shared_theme(mobile: bool = False) -> None:
    max_width = "560px" if mobile else "1180px"
    st.markdown(
        f"""
        <style>
        :root {{
          --color-primary:#1d4ed8; --color-primary-dark:#1e3a8a;
          --color-bg:#f3f6fa; --color-surface:#fff; --color-text:#172033;
          --color-muted:#64748b; --color-border:#d7deea;
          --color-running:#15803d; --color-queued:#2563eb;
          --color-planned:#64748b; --color-warning:#d97706;
          --color-danger:#b91c1c; --color-maintenance:#7c3aed;
        }}
        html,body,.stApp {{
          font-family:"Microsoft YaHei","PingFang SC","Noto Sans SC","Inter","Segoe UI",system-ui,sans-serif;
          color:var(--color-text); background:var(--color-bg); overflow-x:hidden;
        }}
        .block-container {{max-width:{max_width}; padding-top:1rem;}}
        button,[role="button"],input,textarea,[role="combobox"] {{font-size:16px!important;}}
        .stButton>button,div[data-testid="stFormSubmitButton"] button {{
          min-height:48px; border-radius:7px; font-weight:700;
        }}
        .stTextInput input,.stNumberInput input,.stSelectbox div[data-baseweb="select"] {{
          min-height:48px; border-radius:7px;
        }}
        .factory-card {{
          background:var(--color-surface); border:1px solid var(--color-border);
          border-radius:8px; padding:14px; margin:8px 0;
        }}
        .status-text {{font-weight:800;}}
        @media(max-width:600px) {{
          .block-container {{padding-left:12px;padding-right:12px;}}
          h1 {{font-size:1.55rem!important;}}
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )
