# app.py
"""Streamlit application for balanced group distribution."""

import sys
import os
import io

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import streamlit as st
import pandas as pd
from gender_ai import detect_gender, is_name_recognized, get_namsor_api_key
from generator import generate_groups

# Page configuration
st.set_page_config(page_title="РАСХОДИМСЯ ПО ГРУППАМ!", layout="wide")
st.title("🔥 РАСХОДИМСЯ ПО ГРУППАМ!")

# Constants
DATA_KEY = "residents_data"
WIDGET_KEY = "residents_widget"
DEFAULT_COLUMNS = ["Имя", "Пол", "Роль", "🚦 Статус"]
ROLE_OPTIONS = ["Обычный", "ВПИ", "Новичок"]
GENDER_OPTIONS = ["M", "F"]


def initialize_session_state() -> None:
    """Initialize session state with default DataFrame if not present."""
    if DATA_KEY not in st.session_state or not isinstance(
        st.session_state.get(DATA_KEY), pd.DataFrame
    ):
        st.session_state[DATA_KEY] = pd.DataFrame(columns=DEFAULT_COLUMNS)
    if "namsor_debug_log" not in st.session_state:
        st.session_state["namsor_debug_log"] = []


def migrate_roles() -> bool:
    """Migrate old role names to new Russian names. Returns True if migration occurred."""
    df = st.session_state[DATA_KEY]
    if df.empty or "Роль" not in df.columns:
        return False
    
    role_mapping = {"regular": "Обычный", "expert": "ВПИ", "newbie": "Новичок"}
    if df["Роль"].isin(role_mapping.keys()).any():
        df["Роль"] = df["Роль"].replace(role_mapping)
        st.session_state[DATA_KEY] = df.copy()
        if WIDGET_KEY in st.session_state:
            del st.session_state[WIDGET_KEY]
        return True
    return False


def get_current_dataframe() -> pd.DataFrame:
    """Get current dataframe from widget or session state."""
    if WIDGET_KEY in st.session_state and isinstance(
        st.session_state[WIDGET_KEY], pd.DataFrame
    ):
        return st.session_state[WIDGET_KEY]
    return st.session_state.get(DATA_KEY, pd.DataFrame(columns=DEFAULT_COLUMNS))


def add_bulk_names(names_text: str) -> tuple[bool, str]:
    """Add multiple names from text input.
    
    Returns:
        Tuple of (success, message)
    """
    names = [n.strip() for n in names_text.splitlines() if n.strip()]
    if not names:
        return False, "Введите имена для добавления."
    
    df = get_current_dataframe()
    existing_names = set(df["Имя"].dropna().str.strip().tolist())
    unique_names = list(dict.fromkeys(names))
    to_add = [n for n in unique_names if n not in existing_names]
    
    if not to_add:
        return False, "Все имена уже есть в таблице."
    
    # Detect genders and statuses
    genders = []
    statuses = []
    debug_messages = []
    for name in to_add:
        gender_result, success, debug_msg, request_details = detect_gender(name)
        genders.append(gender_result)
        if success:
            statuses.append("Пол определён через ИИ")
        else:
            statuses.append("🔴 Не удалось определить пол")
        debug_messages.append((name, debug_msg, request_details))
        # Add to global debug log with full request/response details
        st.session_state["namsor_debug_log"].append({
            "name": name, 
            "message": debug_msg, 
            "success": success,
            "request_details": request_details
        })
    
    new_rows = pd.DataFrame({
        "Имя": to_add,
        "Пол": genders,
        "Роль": "Обычный",
        "🚦 Статус": statuses
    })
    
    st.session_state[DATA_KEY] = pd.concat([df, new_rows], ignore_index=True)
    if WIDGET_KEY in st.session_state:
        del st.session_state[WIDGET_KEY]
    
    return True, f"✅ Добавлено: {len(to_add)}"


def auto_detect_genders() -> None:
    """Auto-detect gender for all participants."""
    df = get_current_dataframe().copy()
    if df.empty:
        return
    
    # Process each row to get gender, success status, and debug message
    results = df["Имя"].astype(str).apply(detect_gender)
    df["Пол"] = results.apply(lambda x: x[0])
    
    # Collect debug messages
    debug_messages = []
    
    # Set status based on whether Namsor successfully detected the gender
    def get_status_and_debug(name):
        _, success, debug_msg, request_details = detect_gender(name)
        # Add to global debug log with full request/response details
        st.session_state["namsor_debug_log"].append({
            "name": name, 
            "message": debug_msg, 
            "success": success,
            "request_details": request_details
        })
        if success:
            return ("Пол определён через ИИ", debug_msg)
        else:
            return ("🔴 Не удалось определить пол", debug_msg)
    
    status_results = df["Имя"].apply(get_status_and_debug)
    df["🚦 Статус"] = status_results.apply(lambda x: x[0])
    debug_messages = status_results.apply(lambda x: x[1]).tolist()
    
    st.session_state[DATA_KEY] = df
    if WIDGET_KEY in st.session_state:
        del st.session_state[WIDGET_KEY]


def parse_limits(limits_text: str) -> dict[str, list[str]]:
    """Parse limits from text input.
    
    Format: "Name: Other1, Other2" per line
    """
    limits = {}
    for line in limits_text.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key_clean = key.strip()
        if not key_clean:
            continue
        limits[key_clean] = [x.strip() for x in value.split(',') if x.strip()]
    return limits


def render_resident_table() -> pd.DataFrame:
    """Render the resident data editor table."""
    st.subheader("📝 Резиденты")
    
    return st.data_editor(
        st.session_state[DATA_KEY].copy(),
        key=WIDGET_KEY,
        column_config={
            "Имя": st.column_config.TextColumn("Имя", required=True),
            "Пол": st.column_config.SelectboxColumn(
                "Пол", options=GENDER_OPTIONS, required=True, default="M"
            ),
            "Роль": st.column_config.SelectboxColumn(
                "Роль", options=ROLE_OPTIONS, required=True, default="Обычный"
            ),
            "🚦 Статус": st.column_config.TextColumn("Статус", width="small", disabled=True),
        },
        hide_index=True,
        width="stretch",
        num_rows="dynamic"
    )


def render_generation_settings() -> dict:
    """Render generation settings and return values."""
    with st.expander("⚙️ Настройки генерации"):
        return {
            "num_groups": st.number_input("Количество групп", min_value=1, value=2),
            "strict_roles": st.checkbox("Строгий баланс ролей", value=True),
            "strict_genders": st.checkbox("Строгий баланс полов", value=True),
            "seed": st.number_input("Seed (опционально)", value=None, step=1),
        }


def main():
    """Main application entry point."""
    # Initialize session state
    initialize_session_state()
    
    # Check for missing API key and show warning
    if not get_namsor_api_key():
        st.warning("⚠️ **AI-определение пола не работает**: отсутствует переменная окружения `NAMSOR_API_KEY`. "
                  "Пожалуйста, установите её для автоматического определения пола.")
    
    # Run role migration if needed
    if migrate_roles():
        st.rerun()
    
    # Bulk import section
    with st.expander("📋 Массовое добавление резидентов", expanded=True):
        bulk_text = st.text_area(
            "Вставьте список имён (каждое с новой строки)", height=80
        )
        if st.button("➕ Добавить в таблицу", width="stretch"):
            success, message = add_bulk_names(bulk_text)
            if success:
                st.success(message)
                st.rerun()
            else:
                st.warning(message)
    
    # Auto-detect gender button
    if st.button("🔍 Авто-определить пол у всех", type="secondary", width="stretch"):
        auto_detect_genders()
        st.rerun()
    
    # Warning for unrecognized names
    current_df = st.session_state[DATA_KEY]
    if "🚦 Статус" in current_df.columns:
        undetected = current_df[current_df["🚦 Статус"].str.contains("Не удалось определить пол", na=False)]
        if not undetected.empty:
            st.warning(f"🔴 Проверьте вручную: {', '.join(undetected['Имя'])}")
    
    # Always visible Namsor API details section
    st.subheader("📡 Детали коммуникации с Namsor API")
    if st.session_state["namsor_debug_log"]:
        # Display as a table with all entries showing full HTTP request/response details
        log_data = []
        for entry in st.session_state["namsor_debug_log"]:
            if entry["success"]:
                status_text = "Пол определен ИИ"
                status_color = "green"
            else:
                status_text = "Пол не мог быть определён ИИ"
                status_color = "red"
            
            # Format request and response details as JSON-like text
            request_details = entry.get("request_details", {})
            request_info = request_details.get("request", {})
            response_info = request_details.get("response", {})
            
            # Build detailed info string
            details_parts = []
            if request_info:
                details_parts.append(f"<b>Request:</b><br>")
                details_parts.append(f"URL: {request_info.get('url', 'N/A')}<br>")
                details_parts.append(f"Method: {request_info.get('method', 'N/A')}<br>")
                details_parts.append(f"Payload: {request_info.get('payload', {})}<br>")
            
            if response_info:
                details_parts.append(f"<br><b>Response:</b><br>")
                if "error" in response_info:
                    details_parts.append(f"Error: {response_info['error']}<br>")
                else:
                    details_parts.append(f"Status: {response_info.get('status_code', 'N/A')}<br>")
                    details_parts.append(f"Body: {response_info.get('body', {})}<br>")
            
            details_html = "".join(details_parts) if details_parts else entry["message"]
            
            log_data.append({
                "Имя": entry["name"],
                "Статус": f"<span style='color: {status_color}; font-weight: bold;'>{status_text}</span>",
                "Детали": details_html
            })
        log_df = pd.DataFrame(log_data)
        st.dataframe(
            log_df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Статус": st.column_config.TextColumn("Статус"),
                "Детали": st.column_config.TextColumn("Детали", width="large"),
            }
        )
    else:
        st.info("Пока нет записей о коммуникации с Namsor API. Добавьте имена или используйте авто-определение пола.")
    
    # Resident table
    editor_df = render_resident_table()
    
    # Limits section
    st.subheader("🌍 Границы")
    limits_text = st.text_area(
        "Укажите, кто не должен быть в одной группе (Имя: Через запятую)",
        placeholder="Олег С: Леша Ч, Иван П\nАня К: Петя О, Маша И",
        height=240
    )
    
    # Settings
    settings = render_generation_settings()
    
    # Generate button
    st.markdown("---")
    run_button = st.button("🚀 РАСПРЕДЕЛИТЬ!", type="primary", width="stretch")
    
    if run_button:
        # Validate data
        df = editor_df
        if "Имя" not in df.columns or df.empty:
            st.error("Таблица пуста. Добавьте резидентов.")
            st.stop()
        
        valid_df = df.dropna(subset=["Имя"])
        names = valid_df["Имя"].str.strip().tolist()
        
        if len(set(names)) != len(names):
            st.error("В таблице есть дубликаты имён.")
            st.stop()
        
        # Extract data
        genders = dict(zip(valid_df["Имя"].str.strip(), valid_df["Пол"]))
        newbies = valid_df[valid_df["Роль"] == "Новичок"]["Имя"].str.strip().tolist()
        experts = valid_df[valid_df["Роль"] == "ВПИ"]["Имя"].str.strip().tolist()
        limits = parse_limits(limits_text)
        
        try:
            # Generate groups
            result = generate_groups(
                n=settings["num_groups"],
                names=names,
                genders=genders,
                newbies=newbies,
                experts=experts,
                limits=limits,
                seed=int(settings["seed"]) if settings["seed"] else None,
                strict_r=settings["strict_roles"],
                strict_g=settings["strict_genders"],
            )
            
            # Display results
            st.success(f"✅ Seed: {result.used_seed} | Попыток: {result.attempts}")
            if result.warnings:
                st.warning("⚠️ " + "; ".join(result.warnings))
            
            # Create formatted HTML for UI display and styled Excel export
            for i, group in enumerate(result.groups, 1):
                st.subheader(f"Группа {i} ({len(group)} чел.)")
                
                # Format names with styling for UI
                formatted_names = []
                for name in group:
                    name_stripped = name.strip()
                    is_vpi = name_stripped in experts
                    is_newbie = name_stripped in newbies
                    gender = genders.get(name_stripped, "M")
                    
                    # Build HTML with bold for VPI, italic for Newbies, and color for gender
                    # Female = red, Male = blue (UI only)
                    style_parts = []
                    if is_vpi:
                        style_parts.append("font-weight: bold;")
                    if is_newbie:
                        style_parts.append("font-style: italic;")
                    if gender == "F":
                        style_parts.append("color: red;")
                    elif gender == "M":
                        style_parts.append("color: blue;")
                    
                    if style_parts:
                        formatted_names.append(f'<span style="{" ".join(style_parts)}">{name_stripped}</span>')
                    else:
                        formatted_names.append(name_stripped)
                
                st.write(", ".join(formatted_names), unsafe_allow_html=True)
            
            # Export to Excel with formatting (bold/italic only, no colors)
            if result.groups:
                # Create styled Excel using openpyxl
                from openpyxl import Workbook
                from openpyxl.styles import Font, PatternFill
                
                wb = Workbook()
                ws = wb.active
                ws.title = "Группы"
                
                # Create a second sheet for detailed info with status
                ws_details = wb.create_sheet(title="Детали")
                ws_details.append(["Имя", "Пол", "Роль", "Статус", "Группа"])
                
                # Build a lookup for status from the current dataframe
                status_lookup = {}
                role_lookup = {}
                gender_lookup = {}
                current_df = st.session_state[DATA_KEY]
                for _, row in current_df.iterrows():
                    name = row["Имя"].strip() if isinstance(row["Имя"], str) else str(row["Имя"]).strip()
                    status_lookup[name] = row.get("🚦 Статус", "")
                    role_lookup[name] = row.get("Роль", "Обычный")
                    gender_lookup[name] = row.get("Пол", "M")
                
                # Write data and apply formatting
                max_len = max(len(g) for g in result.groups) if result.groups else 0
                for col_idx, group in enumerate(result.groups, 1):
                    col_letter = chr(64 + col_idx)  # A, B, C, ...
                    ws.column_dimensions[col_letter].width = 25
                    
                    for row_idx, name in enumerate(group, 1):
                        cell = ws.cell(row=row_idx, column=col_idx, value=name)
                        
                        # Apply font styling based on role (VPI=bold, Newbie=italic)
                        font_style = Font()
                        if name in experts:
                            font_style = Font(bold=True)
                        if name in newbies:
                            font_style = Font(italic=True)
                        if name in experts and name in newbies:
                            font_style = Font(bold=True, italic=True)
                        
                        cell.font = font_style
                        
                        # Add to details sheet with status
                        name_stripped = name.strip()
                        status = status_lookup.get(name_stripped, "")
                        role = role_lookup.get(name_stripped, "Обычный")
                        gender = gender_lookup.get(name_stripped, "M")
                        
                        # Determine if status indicates failure (red fill)
                        is_failure = "Не удалось определить пол" in status
                        detail_font = Font(color="FF0000" if is_failure else None)
                        detail_fill = PatternFill(start_color="FFFF99", end_color="FFFF99", fill_type="solid") if is_failure else None
                        
                        ws_details.append([name_stripped, gender, role, status, col_idx])
                        # Apply red font and yellow background for failed status
                        status_cell = ws_details.cell(row=ws_details.max_row, column=4)
                        if is_failure:
                            status_cell.font = Font(color="FF0000")
                            status_cell.fill = detail_fill
                    
                    # Add header with count
                    header_cell = ws.cell(row=len(group) + 1, column=col_idx, value=f"({len(group)} чел.)")
                    header_cell.font = Font(italic=True)
                
                # Format details sheet columns
                ws_details.column_dimensions["A"].width = 25
                ws_details.column_dimensions["B"].width = 10
                ws_details.column_dimensions["C"].width = 15
                ws_details.column_dimensions["D"].width = 35
                ws_details.column_dimensions["E"].width = 10
                
                output = io.BytesIO()
                wb.save(output)
                output.seek(0)
                
                st.download_button(
                    "📥 Скачать результат в Excel",
                    data=output,
                    file_name="groups_result.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
        
        except Exception as e:
            st.error(f"❌ {e}")
        
        st.stop()


if __name__ == "__main__":
    main()
