import streamlit as st
from datetime import date
import calendar
import base64
import locale
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import seaborn as sns
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
if "selected_all_projects" not in st.session_state:
    st.session_state["selected_all_projects"] = False

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
    from main import generate_report_pdf_bytes, get_months_range_string, get_months_range_string_en
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

# ====== Language selector ======
if "lang" not in st.session_state:
    st.session_state["lang"] = "DE"

def _on_lang_change():
    # сбросить кэш PDF, чтобы при смене языка заголовок/хедер пересоздались
    st.session_state["pdf_bytes"] = None

st.session_state["lang"] = st.selectbox(
    "Sprache / Language",
    options=["DE", "EN"],
    index=0 if st.session_state["lang"] == "DE" else 1,
    key="lang_select",
    on_change=_on_lang_change
)
# Track last generated language to trigger PDF regen when changed
if "last_lang" not in st.session_state:
    st.session_state["last_lang"] = st.session_state.get("lang", "DE")

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
last_day_of_month  = today.replace(day=calendar.monthrange(today.year, today.month)[1])

if "date_input_key" not in st.session_state:
    st.session_state["date_input_key"] = "date_input_0"

date_range = st.date_input(
    "Wähle den Zeitraum:",
    value=(first_day_of_month, last_day_of_month),
    format="DD.MM.YYYY",
    key=st.session_state["date_input_key"]
)

if isinstance(date_range, (tuple, list)) and len(date_range) == 2:
    start_date, end_date = date_range
else:
    st.error("Bitte wähle einen Zeitraum (Start- und Enddatum).")
    st.stop()

if start_date > end_date:
    st.error("❌ Enddatum darf nicht vor dem Startdatum liegen.")
    st.stop()

if "confirmed_period" not in st.session_state:
    st.session_state["confirmed_period"] = False

if not st.session_state["confirmed_period"]:
    if st.button(
        f"Zeitraum bestätigen",
        key="btn_confirm_period"
    ):
        st.session_state["confirmed_period"] = True
        st.rerun() 
    st.stop()

# ====== Daten nur laden, wenn Zeitraum bestätigt ======
if st.session_state["confirmed_period"] and not st.session_state.get("data_loaded", False):
    from config import API_KEY, WORKSPACE_ID, BASE_URL
    from main   import to_iso_format, get_entries_by_date

    with st.spinner("Lade Daten von Clockify..."):
        start_iso = to_iso_format(start_date.strftime("%d-%m-%Y"), is_end=False)
        end_iso   = to_iso_format(end_date.strftime("%d-%m-%Y"), is_end=True)
        df_date   = get_entries_by_date(
            start_iso, end_iso,
            API_KEY, WORKSPACE_ID, BASE_URL
        )

    if df_date.empty or 'client_name' not in df_date.columns:
        st.warning("Keine Daten im gewählten Zeitraum.")
        st.stop()

    st.session_state["df_date"]   = df_date
    st.session_state["data_loaded"] = True
    st.success(f"{len(df_date)} Einträge geladen.")


# === Wenn Daten geladen ===
if st.session_state.get("data_loaded", False):
    df = st.session_state["df_date"]

# ====== Select client and projects ======
if st.session_state.get("data_loaded", False) and not st.session_state.get("final_confirmed", False):
    st.subheader("Kunden auswählen")

    df_date = st.session_state["df_date"]
    clients = sorted(df_date['client_name'].dropna().unique())
    clients_with_empty = ["Bitte wählen..."] + clients

    if "client_selectbox" not in st.session_state:
        st.session_state["client_selectbox"] = "Bitte wählen..."

    client = st.selectbox(
        "Kunde auswählen:",
        options=clients_with_empty,
        key="client_selectbox"
    )
    if client == "Bitte wählen...":
        st.stop()

    st.session_state["client_selected"] = client

    df_client = df_date[
        df_date["client_name"]
            .str.strip()
            .str.lower() == client.strip().lower()
    ]
    projects = sorted(df_client['project_name'].dropna().unique())

    if "selected_all_projects" not in st.session_state:
        st.session_state["selected_all_projects"] = False

    if st.session_state.get("last_client") != client:
        st.session_state["selected_projects"] = projects if len(projects) == 1 else []
        st.session_state["editor_table"]    = None
        st.session_state["editable_table"]  = None
        st.session_state["last_client"]     = client

    valid = [p for p in st.session_state["selected_projects"] if p in projects]
    st.session_state["selected_projects"] = valid

    if not projects:
        st.warning("Keine Projekte vorhanden.")
        st.stop()

    if len(projects) == 1:
        st.session_state["selected_projects"] = projects
        st.session_state["selected_all_projects"] = True
        st.info(f"Nur ein Projekt verfügbar: **{projects[0]}** automatisch ausgewählt.")
    else:
        # Initialize multiselect state for this client if missing or client changed
        if ("multiselect_projects" not in st.session_state) or (st.session_state.get("last_client") == client and not st.session_state.get("multiselect_projects")):
            st.session_state["multiselect_projects"] = st.session_state["selected_projects"]

        # Apply 'select all' intent BEFORE rendering the multiselect
        if st.session_state.get("force_select_all_projects"):
            st.session_state["multiselect_projects"] = projects
            st.session_state["selected_projects"] = projects
            st.session_state["selected_all_projects"] = True
            st.session_state["force_select_all_projects"] = False

        # Render multiselect using session_state value; do not pass default
        st.multiselect(
            "Verfügbare Projekte:",
            options=projects,
            key="multiselect_projects"
        )
        if st.button("Alle Projekte auswählen", key="btn_select_all_projects"):
            # Set a flag and rerun so we can safely set widget state before it renders
            st.session_state["force_select_all_projects"] = True
            st.rerun()
        else:
            sel = st.session_state.get("multiselect_projects", [])
            # Derive the 'all selected' flag from current selection so user can change it freely
            st.session_state["selected_all_projects"] = (sel == projects)
            st.session_state["selected_projects"] = sel

    if st.session_state["selected_projects"]:
        st.subheader("Überblick")
        st.success(
            f"Zeitraum: {start_date:%d.%m.%Y} – {end_date:%d.%m.%Y}\n\n"
            f"Kunde: {client}\n\n"
            f"Projekte: {', '.join(st.session_state['selected_projects'])}"
        )
        if st.button("Auswahl bestätigen", key="btn_confirm_client"):
            st.session_state["final_confirmed"] = True
            st.rerun()


# ====== Data editor and PDF generation ======
if st.session_state.get("final_confirmed", False):
    st.subheader("Überprüfen und Bearbeiten der Tabelle")

    # Filter table for the current client and projects
    df_selected = st.session_state.df_date[
        (st.session_state.df_date['client_name'] == st.session_state.client_selected) &
        (st.session_state.df_date['project_name'].isin(st.session_state.selected_projects))
    ].sort_values(by='start', key=lambda x: pd.to_datetime(x, dayfirst=True))

    if df_selected.empty:
        st.warning("Keine Einträge gefunden.")
        st.stop()

    editable_df = df_selected[['description', 'task_name', 'start', 'duration_hours']].copy()
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

    # Show total hours WITHOUT manual row
    total_hours = edited_table["duration_hours"].sum()
    st.markdown(f"### Gesamtstunden: **{total_hours:.2f} Stunden**")

    # ====== Optional manual row input ======
    with st.expander("➕ Manuelle Zusatzzeile hinzufügen (optional)", expanded=False):
        manual_description = st.text_input("Beschreibung der Zusatzzeile", "")
        manual_hours = st.number_input("Stunden für Zusatzzeile", min_value=0.0, step=0.25, format="%.2f")

    # Prepare table for PDF
    table_for_pdf = st.session_state.get("editable_table")
    if table_for_pdf is None or table_for_pdf.empty:
        table_for_pdf = edited_table[required_cols].copy()

    if table_for_pdf.empty:
        st.warning("Keine gültigen Daten für PDF-Generierung.")
        st.stop()

    # ===== Einfachste Variante: Gesamtsumme + Balkendiagramm pro Woche =====
    df = table_for_pdf[["start", "duration_hours"]].copy()

    # Типы
    df["start"] = pd.to_datetime(df["start"], dayfirst=True, errors="coerce")
    df["duration_hours"] = pd.to_numeric(
        df["duration_hours"].astype(str).str.replace(",", ".", regex=False),
        errors="coerce"
    )
    df = df.dropna(subset=["start", "duration_hours"])

    if df.empty:
        st.warning("Keine gültigen Daten zum Anzeigen des Diagramms.")
    else:
        # Группировка по ISO‑неделям (понедельник — первый день)
        iso = df["start"].dt.isocalendar()
        weekly = (
            pd.DataFrame({
                "year": iso["year"].astype(int),
                "week": iso["week"].astype(int),
                "hours": df["duration_hours"].values
            })
            .groupby(["year","week"], as_index=False)["hours"].sum()
            .sort_values(["year","week"])
        )

        if not weekly.empty:
            labels = [f"KW {w:02d} ({y})" for y, w in zip(weekly["year"], weekly["week"])]
            total = df["duration_hours"].sum()

            st.markdown("### 📊 Stunden pro Woche")

            fig, ax = plt.subplots(figsize=(10, 5))
            x = range(len(weekly))
            y = weekly["hours"].values
            bars = ax.bar(
                x, y,
                color="#4A90E2",      # мягкий синий
                edgecolor=None,    # обводка
                linewidth=0.1
            )

            # Заголовок и подписи осей
            ax.set_title("Stunden pro Woche", fontsize=14, fontweight="bold", pad=15)
            ax.set_xlabel("Kalenderwoche", fontsize=11)
            ax.set_ylabel("Stunden", fontsize=11)
            ax.set_xticks(list(x))
            ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=9)
            ax.yaxis.set_major_locator(ticker.MaxNLocator(integer=True))
            ax.grid(axis="y", linestyle="--", alpha=0.4)

            pad = (y.max() * 0.02) if len(y) and y.max() > 0 else 0.1
            for bar, value in zip(bars, y):
                ax.text(
                    bar.get_x() + bar.get_width() / 2,  # центр столбика
                    value + pad,
                    f"{value:.1f}",
                    ha="center", va="bottom",
                    fontsize=9,
                    fontweight="bold",
                    color="#333"
                )
            plt.tight_layout()
            st.pyplot(fig)

    # Confirm button
    if st.button("Änderungen bestätigen"):
        st.session_state["editable_table"] = edited_table[required_cols].copy()
        st.session_state["pdf_bytes"] = None
        st.session_state["manual_row"] = None

        # Save manual row to session if valid
        if manual_description and manual_hours > 0:
            st.session_state["manual_row"] = {
                "description": manual_description,
                "task_name": "",
                "start": "",
                "duration_hours": manual_hours
            }
        st.success("Änderungen wurden übernommen!")

    # Add manual row for PDF if exists
    df_for_pdf = table_for_pdf.copy()
  
    # 1. Основные строки для отображения в PDF
    data_rows = [
        [row['description'], row['task_name'], row['start'], f"{row['duration_hours']:.2f}".replace('.', ',')]
        for _, row in df_for_pdf.iterrows()
    ]

    # Добавляем ручную строку, если есть
    manual_row = st.session_state.get("manual_row")
    manual_row_data = None
    if manual_row:
        manual_row_data = [
            manual_row["description"], "", "", f"{manual_row['duration_hours']:.2f}".replace('.', ',')
        ]

    # 3. Считаем total_hours ТОЛЬКО по df_for_pdf
    total_hours = df_for_pdf["duration_hours"].sum()


    # Calculate months and period
    start_vals = pd.to_datetime(table_for_pdf["start"], format="%d.%m.%Y", errors="coerce")
    first_date = start_vals.min()
    last_date = start_vals.max()

    pdf_filename = build_pdf_filename(
        client_name=st.session_state.client_selected,
        selected_projects=st.session_state.selected_projects,
        first_date=first_date,
        last_date=last_date,
        selected_all_projects=st.session_state.get("selected_all_projects", False),
        table_for_pdf=table_for_pdf,  # не df_for_pdf
        lang=st.session_state.get("lang", "DE"),
    )

    # PDF Generation
    lang = st.session_state.get("lang", "DE")
    if (not st.session_state.get("pdf_bytes")) or (st.session_state.get("last_lang") != lang):
        total_hours = table_for_pdf["duration_hours"].sum()
        # Build labels and title per language
        if lang == "EN":
            months_range = get_months_range_string_en(table_for_pdf)
            header_labels = ["Description", "Task", "Date", "Duration"]
            total_label = "Total:"
            title_text = f"Hours statement {months_range}"
        else:
            months_range = get_months_range_string(table_for_pdf)
            header_labels = ["Beschreibung", "Aufgabe", "Datum", "Dauer"]
            total_label = "Gesamtaufwand:"
            title_text = f"Stundenaufstellung {months_range}"

        st.session_state["pdf_bytes"] = generate_report_pdf_bytes(
            logo_path=str(LOGO_PATH),
            company_name=COMPANY_NAME,
            months_range=months_range,
            rows=data_rows,
            total_hours=total_hours,
            manual_row=manual_row_data,
            header_labels=header_labels,
            total_label=total_label,
            title_text=title_text
        )
        # Update last_lang after regeneration
        st.session_state["last_lang"] = lang

    # Download button
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
                "client_selectbox" 
            ]:
                if key in st.session_state:
                    del st.session_state[key]
            st.rerun()
    with col2:
        if st.button("Weitere Kunden"):
            for key in [
                "data_loaded", "df_date", "client_selected", "selected_projects",
                "final_confirmed", "pdf_bytes", "prev_period",
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
