from __future__ import annotations

from config import DEFAULT_PAGE, configure_streamlit


configure_streamlit()

from app_core import (  # noqa: E402
    inject_css,
    login_panel,
    public_bottom_nav,
    public_machine_overview,
    public_top_bar,
    query_flag,
    query_value,
)
from navigation import render_navigation  # noqa: E402
from pages import (  # noqa: E402
    admin_page,
    forecast_page,
    history_page,
    loose_goods_page,
    performance_page,
    machine_page,
    mould_page,
    product_mould_page,
    production_page,
    stock_in_page,
)
from ui_theme import inject_shared_theme  # noqa: E402


def render_selected_page(page: str, machine_id: str) -> None:
    if page == "machine":
        machine_page.render(machine_id)
    elif page == "production_table":
        production_page.render()
    elif page == "stock_in":
        stock_in_page.render()
    elif page == "loose_goods":
        loose_goods_page.render()
    elif page == "moulds":
        mould_page.render()
    elif page == "product_mould_links":
        product_mould_page.render()
    elif page == "history":
        history_page.render()
    elif page == "performance":
        performance_page.render()
    elif page == "forecast":
        forecast_page.render()
    elif page == "admin":
        admin_page.render()
    else:
        machine_page.render(machine_id)


def main() -> None:
    inject_css()
    inject_shared_theme()

    requested_page = query_value("page", DEFAULT_PAGE)
    machine_id = query_value("machine_id", "")
    public_mode = query_flag("public")

    if public_mode and requested_page == "machine":
        public_top_bar()
        if machine_id:
            machine_page.render(machine_id, public_view=True)
        else:
            public_machine_overview()
        public_bottom_nav("machine")
        return

    login_panel()
    page = render_navigation(requested_page)
    render_selected_page(page, machine_id)


if __name__ == "__main__":
    main()
