"""AG Grid rendering for live fleet telemetry."""

from __future__ import annotations

import pandas as pd
import streamlit as st
from st_aggrid import AgGrid, GridOptionsBuilder, JsCode

from config.settings import get_settings
from services.export_service import dataframe_to_csv_bytes, make_export_filename


settings = get_settings()


def render_fleet_grid(frame: pd.DataFrame, theme_mode: str, key: str = "fleet_grid") -> list[dict[str, object]]:
    """Render a professional AG Grid table for live fleet telemetry."""
    if frame.empty:
        st.info("No live fleet rows are available for the selected filters.")
        return []

    searchable = frame.copy()
    searchable["processed_at"] = pd.to_datetime(searchable["processed_at"], errors="coerce").dt.strftime("%Y-%m-%d %H:%M:%S")
    search_value = st.text_input("Search live fleet table", placeholder="Search truck, driver, route, city, or alert...", key=f"{key}_search")
    if search_value:
        mask = searchable.astype(str).apply(lambda column: column.str.contains(search_value, case=False, na=False))
        searchable = searchable[mask.any(axis=1)].reset_index(drop=True)

    st.download_button(
        "Export live fleet CSV",
        data=dataframe_to_csv_bytes(searchable),
        file_name=make_export_filename("fleet_live_table"),
        mime="text/csv",
        use_container_width=True,
    )

    builder = GridOptionsBuilder.from_dataframe(searchable)
    builder.configure_default_column(
        groupable=True,
        value=True,
        enableRowGroup=True,
        editable=False,
        sortable=True,
        filter=True,
        resizable=True,
        floatingFilter=True,
    )
    builder.configure_pagination(enabled=True, paginationPageSize=12)
    builder.configure_selection("multiple", use_checkbox=True)
    builder.configure_side_bar()

    highlight_speed = JsCode(
        """
        function(params) {
            if (params.value >= 145) { return {backgroundColor: 'rgba(244, 63, 94, 0.22)', color: '#ffffff', fontWeight: '700'}; }
            if (params.value >= 120) { return {backgroundColor: 'rgba(245, 158, 11, 0.20)', color: '#ffffff', fontWeight: '700'}; }
            return null;
        }
        """
    )
    highlight_fuel = JsCode(
        """
        function(params) {
            if (params.value <= 10) { return {backgroundColor: 'rgba(244, 63, 94, 0.22)', color: '#ffffff', fontWeight: '700'}; }
            if (params.value <= 20) { return {backgroundColor: 'rgba(245, 158, 11, 0.20)', color: '#ffffff', fontWeight: '700'}; }
            return null;
        }
        """
    )
    highlight_temp = JsCode(
        """
        function(params) {
            if (params.value >= 112) { return {backgroundColor: 'rgba(244, 63, 94, 0.22)', color: '#ffffff', fontWeight: '700'}; }
            if (params.value >= 100) { return {backgroundColor: 'rgba(245, 158, 11, 0.20)', color: '#ffffff', fontWeight: '700'}; }
            return null;
        }
        """
    )
    highlight_alert = JsCode(
        """
        function(params) {
            if (params.value && params.value !== 'NORMAL') { return {backgroundColor: 'rgba(96, 165, 250, 0.18)', fontWeight: '700'}; }
            return null;
        }
        """
    )

    builder.configure_column("speed", type=["numericColumn"], cellStyle=highlight_speed)
    builder.configure_column("fuel_level", type=["numericColumn"], cellStyle=highlight_fuel)
    builder.configure_column("engine_temp", type=["numericColumn"], cellStyle=highlight_temp)
    builder.configure_column("alert_type", cellStyle=highlight_alert)
    builder.configure_column("theft", header_name="theft", type=["textColumn"])
    builder.configure_column("driver_id", header_name="driver_id")
    builder.configure_column("processed_at", sort="desc")

    response = AgGrid(
        searchable,
        gridOptions=builder.build(),
        allow_unsafe_jscode=True,
        fit_columns_on_grid_load=False,
        theme="streamlit" if theme_mode == "light" else "alpine-dark",
        height=465,
        key=key,
        enable_enterprise_modules=False,
        reload_data=False,
    )
    return response.get("selected_rows", []) if isinstance(response, dict) else []
