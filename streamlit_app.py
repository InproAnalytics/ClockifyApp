import streamlit as st
from datetime import date
import calendar
import base64
import pandas as pd
import os
from main import LOGO_PATH, COMPANY_NAME

# ====== Check environment ======
st.set_page_config(page_title="Clockify Berichtgenerator", layout="centered")

is_cloud = (
    os.getenv("STREAMLIT_SERVER_HEADLESS") == "1" or
    "X-Amzn-Trace-Id" in os.environ
)

# ====== Initialize authentication state ======
if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False

# ====== Login form ======
if not st.session_state["authenticated"]:
    st.title("🔐 Clockify Bericht Anmeldung")
    username = st.text_input("Benutzername")
    password = st.text_input("Passwort", type="password")

    if st.button("Anmelden"):
        auth_users = st.secrets.get("auth", {})
        if username in auth_users and auth_users[username]["password"] == password:
            user_secrets = st.secrets.get("users", {}).get(username)
            if user_secrets:
                st.session_state.update({
                    "authenticated": True,
                    "username": username,
                    "api_key": user_secrets["api_key"],
                    "workspace_id": user_secrets["workspace_id"],
                    "base_url": user_secrets.get("base_url", "https://api.clockify.me/api/v1")
                })
                st.rerun()
            else:
                st.error("🚫 Benutzer hat keinen API-Zugriff.")
        else:
            st.error("❌ Ungültige Anmeldedaten.")
    st.stop()
# ====== Hide Streamlit UI elements ======
st.markdown(
    """
    <style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    .block-container { padding-top: 2rem; }
    h1, h2, h3, h4 { color: #2c3e50; }
    </style>
    """,
    unsafe_allow_html=True
)

# ====== API configuration ======
if st.session_state.get("authenticated"):
    from config import API_KEY, WORKSPACE_ID, BASE_URL
    from main import to_iso_format, get_entries_by_date
    from main import generate_report_pdf_bytes, get_months_range_string
    from main import build_pdf_filename

    API_KEY = st.session_state["api_key"]
    WORKSPACE_ID = st.session_state["workspace_id"]
    BASE_URL = st.session_state.get("base_url", "https://api.clockify.me/api/v1")

    if not all([API_KEY, WORKSPACE_ID, BASE_URL]):
        st.error("❌ Unvollständige API-Konfiguration. Überprüfen Sie `secrets.toml`.")
        st.stop()

# ====== Custom style ======
st.markdown(
    """
    <style>
    .block-container { padding-top: 2rem; }
    h1, h2, h3, h4 { color: #2c3e50; }
    </style>
    """,
    unsafe_allow_html=True
)

# ====== Encode logo ======
def get_image_base64(path):
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()

logo_base64 = get_image_base64(LOGO_PATH)

# ====== Header ======
st.markdown(
    f"""
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom:1rem;">
        <h2 style="margin: 0;">{COMPANY_NAME}</h2>
        <img src="data:image/png;base64,{logo_base64}" width="100" />  
    </div>
    <h3 style="margin: 0;">PDF-Bericht</h3>
    <hr style="margin-top:1rem;margin-bottom:1.5rem;">
    """,
    unsafe_allow_html=True
)

username = st.session_state.get("username", "Benutzer")
st.markdown(f"👋 Willkommen, **{username.capitalize()}**!")

# ====== Session state initialization ======
for key in [
    "zeitraum_confirmed", "data_loaded", "df_date", "client_selected",
    "selected_projects", "final_confirmed", "pdf_bytes"
]:
    if key not in st.session_state:
        st.session_state[key] = pd.DataFrame() if key == "df_date" else ([] if key == "selected_projects" else False)

# ====== Select time range ======
st.subheader("Zeitraum auswählen")

today = date.today()
first_day_of_month = today.replace(day=1)
last_day_of_month = today.replace(day=calendar.monthrange(today.year, today.month)[1])

import streamlit as st
from datetime import date

# === Dynamischer Schlüssel für date_input ===
if "date_input_key" not in st.session_state:
    st.session_state["date_input_key"] = "date_input_0"

# === Datumsauswahl ===
date_range = st.date_input(
    "Wähle den Zeitraum:",
    value=(first_day_of_month, last_day_of_month),
    format="DD.MM.YYYY",
    key=st.session_state["date_input_key"]
)

# === Validierung des Zeitraums ===
if isinstance(date_range, (tuple, list)) and len(date_range) == 2:
    start_date, end_date = date_range
else:
    st.error("Bitte wähle einen Zeitraum (Start- und Enddatum).")
    st.stop()

if start_date > end_date:
    st.error("❌ Enddatum darf nicht vor dem Startdatum liegen.")
    st.stop()

# === Автосброс подтверждённого периода при изменении дат ===
temp_period = {"start": start_date, "end": end_date}
confirmed = st.session_state.get("confirmed_period")

if confirmed and (confirmed["start"] != start_date or confirmed["end"] != end_date):
    st.session_state["confirmed_period"] = None
    st.session_state["data_loaded"] = False

# === Bestätigungsbutton ===
if st.button("Zeitraum bestätigen"):
    st.session_state["confirmed_period"] = {"start": start_date, "end": end_date}
    st.session_state["data_loaded"] = False  # Trigger Neuladen bei Bestätigung

# === Daten nur laden, wenn bestätigt ===
confirmed = st.session_state.get("confirmed_period")

if confirmed:
    start_date = confirmed["start"]
    end_date   = confirmed["end"]

    prev = st.session_state.get("prev_period", {})
    if not isinstance(prev, dict):
        prev = {}

    # Wenn der bestätigte Zeitraum anders ist -> Reset
    if (prev.get("start"), prev.get("end")) != (start_date, end_date):
        st.session_state["data_loaded"] = False
        st.session_state["df_date"]      = None
        st.session_state["client_selected"]   = None
        st.session_state["selected_projects"] = []
        st.session_state["final_confirmed"]   = False
        st.session_state["pdf_bytes"]         = None
        st.session_state["prev_period"]       = {"start": start_date, "end": end_date}
        st.session_state["editor_table"] = None
        st.session_state["editable_table"] = None

    # Daten laden, wenn noch nicht geschehen
    if not st.session_state.get("data_loaded", False):
        from config import API_KEY, WORKSPACE_ID, BASE_URL
        from main import to_iso_format, get_entries_by_date
        with st.spinner("Lade Daten von Clockify..."):
            start_iso = to_iso_format(start_date.strftime("%d-%m-%Y"), is_end=False)
            end_iso   = to_iso_format(end_date.strftime("%d-%m-%Y"), is_end=True)
            df_date   = get_entries_by_date(start_iso, end_iso, API_KEY, WORKSPACE_ID, BASE_URL)
        if df_date.empty or 'client_name' not in df_date.columns:
            st.warning("Keine Daten im gewählten Zeitraum.")
            st.stop()
        else:
            st.session_state["df_date"]     = df_date
            st.session_state["data_loaded"] = True

# === Wenn Daten geladen ===
if st.session_state.get("data_loaded", False):
    df = st.session_state["df_date"]
    st.write("Geladene Einträge insgesamt:", len(st.session_state["df_date"]))

# ====== Select client and projects ======
if st.session_state.data_loaded and not st.session_state.final_confirmed:
    st.subheader("Kunden auswählen")

    df_date = st.session_state.df_date
    clients = sorted(df_date['client_name'].dropna().unique())
    clients_with_empty = ["Bitte wählen..."] + clients

    # Если сброшено, то selectbox всегда будет пустой!
    if "client_selectbox" not in st.session_state:
        st.session_state["client_selectbox"] = "Bitte wählen..."

    client = st.selectbox(
        "Kunde auswählen:",
        options=clients_with_empty,
        key="client_selectbox"
    )

    # Не продолжаем, если не выбран клиент
    if client == "Bitte wählen...":
        st.stop()
    
    # Далее используем только client
    # ...

    # ✅ FIX: убрано st.session_state["client_selected"]
    client_selected = client
    df_client = df_date[df_date["client_name"].str.strip().str.lower() == client.strip().lower()]

    # Projects
    df_client = df_date[df_date['client_name'] == client_selected]
    projects = sorted(df_client['project_name'].dropna().unique())
    if "last_client" not in st.session_state or st.session_state["last_client"] != client_selected:
        st.session_state["selected_projects"] = projects if len(projects) == 1 else []
        st.session_state["editor_table"] = None
        st.session_state["editable_table"] = None
        st.session_state["last_client"] = client_selected  # сохраняем текущий

    valid_selected_projects = [p for p in st.session_state.selected_projects if p in projects]
    st.session_state.selected_projects = valid_selected_projects

    if not projects:
        st.warning("Keine Projekte vorhanden.")
        st.stop()

    valid_selected_projects = [p for p in st.session_state.selected_projects if p in projects]
    st.session_state.selected_projects = valid_selected_projects

    if len(projects) == 1:
        selected_projects = projects
        st.info(f"Nur ein Projekt verfügbar: **{projects[0]}** wird automatisch ausgewählt.")
    else:
        selected_projects = st.multiselect(
            "Verfügbare Projekte:",
            options=projects,
            default=valid_selected_projects
        )
        if st.button("Alle Projekte auswählen"):
            selected_projects = projects

    st.session_state.selected_projects = selected_projects

    # Overview
    if selected_projects and not st.session_state.final_confirmed:
        st.subheader("Überblick")
        st.success(
            f"Zeitraum: {start_date.strftime('%d.%m.%Y')} bis {end_date.strftime('%d.%m.%Y')}\n\n"
            f"Kunde: {client_selected}\n\nProjekte: {', '.join(selected_projects)}"
        )
        if st.button("Auswahl bestätigen"):
            st.session_state.final_confirmed = True

# ====== Data editor and PDF generation ======
if st.session_state.final_confirmed and \
   st.session_state.get("client_selectbox", None) and \
   st.session_state["client_selectbox"] != "Bitte wählen...":

    client = st.session_state["client_selectbox"]

    # Filter the table for the current client and projects
    df_selected = st.session_state.df_date[
        (st.session_state.df_date['client_name'].str.strip().str.lower() == client.strip().lower()) &
        (st.session_state.df_date['project_name'].isin(st.session_state.selected_projects))
    ].sort_values(by='start', key=lambda x: pd.to_datetime(x, dayfirst=True))  # ✅ FIX: client_selectbox

    if df_selected.empty:
        st.warning("Keine Einträge gefunden.")
        st.stop()

    editable_df = df_selected[['description', 'task_name', 'start', 'duration_hours']].copy()

    # Always reset the editor_table for a new client/period/project selection
    st.session_state["editor_table"] = editable_df.copy()

    # Data editor widget
    edited_table = st.data_editor(
        st.session_state["editor_table"],
        num_rows="dynamic",
        use_container_width=True,
        key="editor"
    )

    required_cols = ["description", "task_name", "start", "duration_hours"]
    missing = [col for col in required_cols if col not in edited_table.columns]

    if missing:
        st.error(f"Spalte(n) fehlt/fehlen in der Tabelle: {', '.join(missing)}. Die PDF-Erstellung ist nicht möglich.")
        st.stop()

    # Confirm changes
    if st.button("Änderungen bestätigen"):
        st.session_state["editable_table"] = edited_table[required_cols].copy()
        st.session_state["pdf_bytes"] = None
        st.success("Änderungen wurden übernommen und werden im PDF verwendet!")

    # Prepare table for PDF: always take current edits if exist, otherwise editor view
    table_for_pdf = st.session_state.get("editable_table")
    if table_for_pdf is None or not hasattr(table_for_pdf, "empty") or table_for_pdf.empty:
        table_for_pdf = edited_table[required_cols].copy()

    # Defensive check for empty DataFrame
    if table_for_pdf is None or not hasattr(table_for_pdf, "empty") or table_for_pdf.empty:
        st.warning("Keine gültigen Daten für PDF-Generierung.")
        st.stop()

    # PDF Download section
    st.subheader("PDF-Download")
    if not st.session_state.get("pdf_bytes"):
        months_range = get_months_range_string(table_for_pdf)
        total_hours = table_for_pdf['duration_hours'].sum()
        data_rows = [
            [row['description'], row['task_name'], row['start'], f"{row['duration_hours']:.2f}".replace('.', ',')]
            for _, row in table_for_pdf.iterrows()
        ]
        st.session_state["pdf_bytes"] = generate_report_pdf_bytes(
            logo_path=str(LOGO_PATH),
            company_name=COMPANY_NAME,
            months_range=months_range,
            rows=data_rows,
            total_hours=total_hours
        )

    # Prepare filename using dates in table
    first_date = pd.to_datetime(table_for_pdf["start"], dayfirst=True).min()
    last_date = pd.to_datetime(table_for_pdf["start"], dayfirst=True).max()
    pdf_filename = build_pdf_filename(
        st.session_state["client_selectbox"],  # ✅ FIX
        st.session_state["selected_projects"],
        first_date,
        last_date
    )

    st.download_button(
        label="📥 PDF herunterladen",
        data=st.session_state["pdf_bytes"],
        file_name=pdf_filename,
        mime="application/pdf"
    )

# ====== Navigation ======
if st.session_state.get("pdf_bytes"): 
    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("Neuer Zeitraum"):
            st.session_state["confirmed_period"] = None
            num = int(st.session_state["date_input_key"].split("_")[-1])
            st.session_state["date_input_key"] = f"date_input_{num+1}"

            for key in [
                "data_loaded", "df_date",
                "selected_projects", "final_confirmed",
                "pdf_bytes", "prev_period",
                "editor_table", "editable_table",
                "client_selectbox"  # ✅ теперь точно сбросится до отрисовки
            ]:
                if key in st.session_state:
                    del st.session_state[key]
            st.rerun()

    with col2:
        if st.button("Weitere Kunden"):
            for key in [
                "client_selectbox",  # ✅ гарантированно сбрасывается
                "selected_projects",
                "final_confirmed", "pdf_bytes",
                "editor_table", "editable_table"
            ]:
                if key in st.session_state:
                    del st.session_state[key]
            st.rerun()

    with col3:
        if st.button("Beenden"):
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.session_state["authenticated"] = False
            st.rerun()
