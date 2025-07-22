import streamlit as st
from datetime import date
import calendar
import base64
import pandas as pd
import requests
import hashlib
import os
from main import LOGO_PATH, COMPANY_NAME


# ====== Verify execution environment ======
is_cloud = (
    os.getenv("STREAMLIT_SERVER_HEADLESS") == "1" or
    "X-Amzn-Trace-Id" in os.environ
)

# ====== Authentication ======

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

# 👉 FIRST — initialize authentication state
if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False

# 👉 THEN check authentication status
if not st.session_state["authenticated"]:
    st.set_page_config(page_title="Clockify Anmeldung", layout="centered")
    st.title("🔐 Clockify Bericht Anmeldung")

    username = st.text_input("Benutzername")
    password = st.text_input("Passwort", type="password")

    if st.button("Anmelden"):
        auth_users = st.secrets.get("auth", {})
        st.write("Verfügbare Benutzer:", list(auth_users.keys()))

        if username in auth_users:
            stored_hash = auth_users[username]["password_hash"]
            if stored_hash == hash_password(password):
                user_secrets = st.secrets.get("users", {}).get(username)
                if user_secrets:
                    st.session_state["api_key"] = user_secrets["api_key"]
                    st.session_state["workspace_id"] = user_secrets["workspace_id"]
                    st.session_state["base_url"] = user_secrets.get("base_url", "https://api.clockify.me/api/v1")
                    st.session_state["username"] = username
                    st.session_state["authenticated"] = True
                    st.rerun()
                else:
                    st.error("🚫 Benutzer hat keinen API-Zugriff.")
            else:
                st.error("❌ Ungültiges Passwort.")
        else:
            st.error("❌ Benutzer nicht gefunden.")

    st.stop()

# ====== API Configuration ======
if st.session_state["authenticated"]:
    import config
    from main import to_iso_format, get_entries_by_date
    from main import generate_report_pdf_bytes, get_months_range_string
    from main import build_pdf_filename

    API_KEY = st.session_state.get("api_key")
    WORKSPACE_ID = st.session_state.get("workspace_id")
    BASE_URL = st.session_state.get("base_url", "https://api.clockify.me/api/v1")

    # Verify API settings
    if not all([API_KEY, WORKSPACE_ID, BASE_URL]):
        st.error("❌ Unvollständige API-Konfiguration. Überprüfen Sie `secrets.toml` oder `.env`.")
        st.stop()

# === Page configuration ===
st.set_page_config(page_title="Clockify Berichtgenerator", layout="centered", initial_sidebar_state="auto")

# === Custom Style (Business Light Theme) ===
st.markdown(
    """
    <style>
    .block-container {
        padding-top: 2rem;
    }
    h1, h2, h3, h4 {
        color: #2c3e50;
    }
    </style>
    """,
    unsafe_allow_html=True
)

# === Encode logo ===
def get_image_base64(path):
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()

logo_base64 = get_image_base64(LOGO_PATH)

# === Header ===
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

# === Greeting ===
username = st.session_state.get("username", "Benutzer")
st.markdown(f"👋 Willkommen, **{username.capitalize()}**!  ")  # Plain text to avoid framed box

# === Initialize session state ===
for key in [
    "zeitraum_confirmed", "data_loaded", "df_date", "client_selected",
    "selected_projects", "final_confirmed", "pdf_bytes"
]:
    if key not in st.session_state:
        st.session_state[key] = pd.DataFrame() if key == "df_date" else ([] if key == "selected_projects" else False)

# === Select time range ===
st.subheader("Zeitraum auswählen")

today = date.today()
first_day_of_month = today.replace(day=1)
last_day_of_month = today.replace(day=calendar.monthrange(today.year, today.month)[1])

date_range = st.date_input(
    "Wähle den Zeitraum:",
    value=(first_day_of_month, last_day_of_month),
    format="DD.MM.YYYY"
)

if isinstance(date_range, tuple) and len(date_range) == 2:
    start_date, end_date = date_range
else:
    st.error("⚠️ Bitte wähle einen Zeitraum (Start- und Enddatum).")
    st.stop()

if start_date > end_date:
    st.error("❌ Enddatum darf nicht vor dem Startdatum liegen.")
    st.stop()

# Reset, falls sich der Zeitraum geändert hat
prev = st.session_state.get("prev_period", {})
if prev.get("start") != start_date or prev.get("end") != end_date:
    for key in ["data_loaded", "client_selected", "selected_projects", "final_confirmed", "pdf_bytes"]:
        st.session_state[key] = False if isinstance(st.session_state.get(key), bool) else []
    # merken
    st.session_state["prev_period"] = {"start": start_date, "end": end_date}

# ────────────────────────────────────────────────────
# 1) Detect change of date_range and reset dependent state
# ────────────────────────────────────────────────────

# lade vorherige Werte (falls schon gesetzt)
prev_start = st.session_state.get("prev_start")
prev_end   = st.session_state.get("prev_end")

# falls sich eines der beiden Datumswerte geändert hat, alle Abhängigen resetten
if (prev_start and start_date != prev_start) or (prev_end and end_date != prev_end):
    st.session_state.data_loaded       = False
    st.session_state.client_selected   = None
    st.session_state.selected_projects = []
    st.session_state.final_confirmed   = False
    st.session_state.pdf_bytes         = None

# speichere aktuellen Zeitraum für die nächste Iteration
st.session_state.prev_start = start_date
st.session_state.prev_end   = end_date

# === Load data ===
if not st.session_state.data_loaded:
    load_click = st.button("Daten laden")
    # если не нажали — останавливаем рендер, дальше не пускать
    if not load_click:
        st.stop()

    # здесь мы знаем, что кнопку нажали — грузим данные
    with st.spinner("Lade Daten von Clockify..."):
        try:
            start_iso = to_iso_format(start_date.strftime("%d-%m-%Y"), is_end=False)
            end_iso   = to_iso_format(end_date.strftime("%d-%m-%Y"), is_end=True)
            df_date   = get_entries_by_date(start_iso, end_iso, API_KEY, WORKSPACE_ID, BASE_URL)
        except requests.exceptions.RequestException as e:
            st.error(f"Netzwerkfehler: {e}")
            st.stop()

    if df_date.empty or 'client_name' not in df_date.columns:
        st.warning("Keine Daten im gewählten Zeitraum.")
        st.stop()

    # сохраняем и отмечаем, что загрузили
    st.session_state.df_date      = df_date
    st.session_state.data_loaded  = True
    st.success(f"{len(df_date)} Einträge geladen.")

# === Select client ===
if st.session_state.data_loaded and not st.session_state.final_confirmed:
    st.subheader("Client auswählen")
    df_date = st.session_state.df_date
    clients = sorted(df_date['client_name'].dropna().unique())

    if not clients:
        st.warning("Keine Kunden vorhanden.")
        st.stop()

    default_index = clients.index(st.session_state.client_selected) if st.session_state.client_selected in clients else 0
    client_selected = st.selectbox("Kunde:", options=clients, index=default_index)
    st.session_state.client_selected = client_selected

    # === Select projects ===
    df_client = df_date[df_date['client_name'] == client_selected]
    projects = sorted(df_client['project_name'].dropna().unique())

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

    # === Overview ===
    if selected_projects and not st.session_state.final_confirmed:
        st.subheader("Überblick")
        st.success(
            f"Zeitraum: {start_date.strftime('%d.%m.%Y')} bis {end_date.strftime('%d.%m.%Y')}\n\n"
            f"Client: {client_selected}\n\nProjekte: {', '.join(selected_projects)}"
        )
        if st.button("Auswahl bestätigen"):
            st.session_state.final_confirmed = True




# === PDF Download ===
if st.session_state.final_confirmed:
    st.subheader("PDF-Download")

    df_selected = st.session_state.df_date[
        (st.session_state.df_date['client_name'] == st.session_state.client_selected) &
        (st.session_state.df_date['project_name'].isin(st.session_state.selected_projects))
    ].sort_values(by='start', key=lambda x: pd.to_datetime(x, dayfirst=True))

    if df_selected.empty:
        st.warning("Keine Einträge gefunden.")
        st.stop()

    if not st.session_state.pdf_bytes:
        months_range = get_months_range_string(df_selected)
        total_hours = df_selected['duration_hours'].sum()
        data_rows = [
            [row['description'], row['task_name'], row['start'], f"{row['duration_hours']:.2f}".replace('.', ',')]
            for _, row in df_selected.iterrows()
        ]
        st.session_state.pdf_bytes = generate_report_pdf_bytes(
            logo_path=str(LOGO_PATH),
            company_name=COMPANY_NAME,
            months_range=months_range,
            rows=data_rows,
            total_hours=total_hours
        )

    first_date = pd.to_datetime(df_selected["start"], dayfirst=True).min()
    last_date = pd.to_datetime(df_selected["start"], dayfirst=True).max()
    pdf_filename = build_pdf_filename(
        st.session_state.client_selected,
        st.session_state.selected_projects,
        first_date,
        last_date
    )

    st.download_button(
        label="📥 PDF herunterladen",
        data=st.session_state.pdf_bytes,
        file_name=pdf_filename,
        mime="application/pdf"
    )

# === Navigation ===
if st.session_state.get("pdf_bytes"):
    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("Neuer Zeitraum"):
            for key in ["data_loaded", "df_date", "client_selected", "selected_projects", "final_confirmed", "pdf_bytes"]:
                st.session_state[key] = [] if key == "selected_projects" else (pd.DataFrame() if key == "df_date" else False)
            st.rerun()
    with col2:
        if st.button("Weitere Kunden"):
            for key in ["client_selected", "selected_projects", "final_confirmed", "pdf_bytes"]:
                st.session_state[key] = [] if key == "selected_projects" else False
            st.rerun()
    with col3:
        if st.button("Beenden"):
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.session_state["authenticated"] = False
            st.rerun()
