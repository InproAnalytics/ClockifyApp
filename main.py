from collections import defaultdict
from datetime import datetime
from jinja2 import Template
from pathlib import Path
import pandas as pd

import requests
from weasyprint import HTML, CSS
import locale
import sys
import re
import os

API_KEY      = 'NmYxYzcxZDItYTk2OS00MjljLTlhMzktYWE2ZWRmZTg0Njc5'
# API_KEY      = 'ZTlkNGRlNzQtZDBkMy00NDY0LWEyZTQtMzdhZTQ0YjlmOWM4'
WORKSPACE_ID = '66052c545402842181578e74'
BASE_URL     = "https://api.clockify.me/api/v1"
HEADERS      = {'X-Api-Key': API_KEY, 'Content-Type': 'application/json'}

PAGE_SIZE = 1000

def to_iso_format(date_str: str, is_end=False) -> str:
    """
    Parse a human-friendly date string in formats:
       - DD-MM, DD.MM, DD/MM
       - DD-MM-YYYY, DD.MM.YYYY, DD/MM/YYYY
       - YYYY-MM-DD
    and return an ISO string:
       'YYYY-MM-DDT00:00:00Z'  (if is_end=False)
       'YYYY-MM-DDT23:59:59Z'  (if is_end=True).
    Raises ValueError on unsupported format.
    """
    date_str = date_str.strip()
    today = datetime.now()

    # Pattern for DD-MM(-YYYY), DD.MM(.YYYY) or DD/MM(/YYYY)
    m = re.match(r'^(\d{1,2})[.\-/](\d{1,2})(?:[.\-/](\d{4}))?$', date_str)
    if m:
        d, mo, y = m.groups()
        day, mon = int(d), int(mo)
        year     = int(y) if y else today.year
    else:
        # Fallback for strict YYYY-MM-DD
        try:
            dt0 = datetime.strptime(date_str, "%Y-%m-%d")
            day, mon, year = dt0.day, dt0.month, dt0.year
        except Exception:
            raise ValueError(f"Unsupported date format: '{date_str}'")

    # Build datetime at day boundary
    if is_end:
        dt = datetime(year, mon, day, 23, 59, 59)
    else:
        dt = datetime(year, mon, day, 0,  0,  0)

    # Return ISO8601 string with 'Z'
    return dt.isoformat(timespec="seconds") + "Z"


def fetch_all(endpoint: str, params: dict = None) -> list:
    """
    Fetch all pages from Clockify API. Returns a flat list of JSON objects.
    Raises RequestException on network or HTTP errors.
    """
    items = []
    page = 1
    session = requests.Session()
    default_params = {"page-size": PAGE_SIZE, "hydrated": True}
    
    while True:
        query = {**default_params, "page": page}
        if params:
            query.update(params)
        resp = session.get(f"{BASE_URL}{endpoint}",
                           headers=HEADERS,
                           params=query,
                           timeout=10)
        resp.raise_for_status()
        batch = resp.json()
        if not batch:
            break
        items.extend(batch)
        page += 1

    return items


def get_entries_by_date(start_iso: str, end_iso: str) -> pd.DataFrame:
    """
    Return a DataFrame of all time entries between start_iso and end_iso,
    including client_id and project_id for downstream logic.
    """
    users = fetch_all(f"/workspaces/{WORKSPACE_ID}/users")
    if not users:
        return pd.DataFrame()

    frames = []
    for user in users:
        # Fetch this user's time entries in the given date range
        entries = fetch_all(
            f"/workspaces/{WORKSPACE_ID}/user/{user['id']}/time-entries",
            params={"start": start_iso, "end": end_iso}
        )
        if not entries:
            continue

        # Normalize JSON into a flat DataFrame
        df = pd.json_normalize(entries, sep='.')

        # Extract IDs for later use
        df['description'] = df.get('description', pd.NA).fillna('').astype(str)
        df['client_id']  = df.get('project.clientId', pd.NA).fillna('').astype(str)
        df['project_id'] = df.get('projectId',       pd.NA).fillna('').astype(str)

        # Add user, client, project and task names
        df['user_name']    = user['name']
        df['client_name']  = df.get('project.clientName', '').fillna('').astype(str)
        df['project_name'] = df.get('project.name',       '').fillna('').astype(str)
        df['task_name'] = df.get('task.name', pd.Series(dtype='object')).fillna('').astype(str)


        # Format the start timestamp as DD.MM.YYYY
        df['start'] = pd.to_datetime(df['timeInterval.start'], errors='coerce').dt.strftime('%d.%m.%Y')

        # Calculate duration in hours as a float
        df['duration_hours'] = (
            pd.to_datetime(df['timeInterval.end'])
          - pd.to_datetime(df['timeInterval.start'])
        ).dt.total_seconds() / 3600

        # Keep only the columns we need downstream
        frames.append(df[[
            'description',
            'user_name',
            'client_id',
            'client_name',
            'project_id',
            'project_name',
            'task_name',
            'start',
            'duration_hours'
        ]])

    # Combine all user frames into one DataFrame, or return empty if none
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def build_client_name_map(clients: list[dict]) -> dict[str, list[str]]:
    """
    Build a mapping from lowercase client name to list of client IDs.
    Pure function: deterministic, no side effects.
    """
    mp: dict[str, list[str]] = defaultdict(list)
    for c in clients:
        name = c['name'].lower()
        mp[name].append(c['id'])
    return mp


def select_client_id(name_map: dict[str, list[str]], choice: str) -> str:
    """
    Given a name_map and a lowercase choice string,
    return the single client_id or raise:
      - KeyError       if choice not in name_map
      - ValueError     if choice maps to multiple IDs
    Pure function.
    """
    if choice not in name_map:
        raise KeyError(f"No such client: '{choice}'")
    ids = name_map[choice]
    if len(ids) > 1:
        raise ValueError(f"Ambiguous client '{choice}': {ids}")
    return ids[0]


def filter_by_client(df: pd.DataFrame, client_name: str) -> pd.DataFrame:
    """Pure: filter DataFrame by client_name (case-insensitive)."""
    key = client_name.lower()
    return df[df['client_name'].str.lower() == key].copy()


def filter_by_client_inter(df: pd.DataFrame) -> pd.DataFrame:
    """
    Interactive loop: prompt user until a valid client is selected.
    Uses pure helpers to do the actual lookup.
    """
    # 1) fetch clients and build pure map
    clients = fetch_all(f"/workspaces/{WORKSPACE_ID}/clients")
    name_map = build_client_name_map(clients)

    while True:
        choice = input("Client name (exact, or 'x' to quit): ").strip().lower()
        if choice == 'x':
            print("⛔ Cancelled by user.")
            sys.exit(0)
        # 2) attempt pure lookup
        try:
            client_id = select_client_id(name_map, choice)
        except KeyError:
            print(f"❌ Client '{choice}' not found. Available: {sorted(name_map)}")
            continue
        except ValueError as e:
            print(f"❌ {e}. Please disambiguate.")
            continue

        # 3) filter DataFrame and verify non-empty
        df_client = df[
            (df['client_name'].str.lower() == choice) &
            (df['client_id'] == client_id)
        ]
        if df_client.empty:
            print(f"❌ No entries for '{choice}' in this period. Try another.")
            continue

        # 4) success!
        return df_client.copy()


def filter_by_project(df: pd.DataFrame, project_name: str) -> pd.DataFrame:
    """
    Pure: filter df by project_name (case-insensitive), no I/O.
    """
    key = project_name.lower()
    return df[df['project_name'].str.lower() == key].copy()


def filter_by_project_inter(df: pd.DataFrame) -> pd.DataFrame:
    """
    Interactive: prompt for project name, then filter via filter_df_by_project.
    """
    available = sorted(df['project_name'].dropna().unique())
    available_lower = [p.lower() for p in available]

    while True:
        choice = input("Project name (exact, or 'x' to quit): ").strip()
        if choice.lower() == 'x':
            print("⛔ Cancelled by user.")
            sys.exit(0)
        if choice.lower() not in available_lower:
            print("No such project. Available:", available)
            continue

        return filter_by_project(df, choice)


def get_data(client: str, project: str, start: str, end: str) -> pd.DataFrame:
    """Fetch and filter time entries based on client, project, and date range."""
    start_iso = to_iso_format(start, is_end=False)
    end_iso   = to_iso_format(end,   is_end=True)

    df_date   = get_entries_by_date(start_iso, end_iso)
    print(df_date[['user_name','start','project_id']].head())
    print("DEBUG: unique client names in df_date:", sorted(df_date['client_name'].dropna().unique().tolist()))

    df_client = filter_by_client(df_date, client)
    df_proj   = filter_by_project(df_client, project)
    return df_proj


def render_report_html(df, client, project, months_range, total_hours, template_path, logo_url) -> str:
    """
    Rendert den HTML-Report als String.
    """

    # Tabelle vorbereiten
    df_display = (
        df[["description", "task_name", "start", "duration_hours"]]
        .rename(columns={
            "description": "Beschreibung",
            "task_name":   "Aufgabe",
            "start":       "Datum",
            "duration_hours": "Dauer"
        })
        .fillna("")
    )
    df_display['Dauer'] = pd.to_numeric(df_display['Dauer'], errors='coerce')
    df_display['Dauer'] = df_display['Dauer'].fillna(0).apply(lambda x: f"{x:.2f}".replace('.', ','))
    df_display['_dt'] = pd.to_datetime(df_display['Datum'], format='%d.%m.%Y', dayfirst=True)
    df_display = df_display.sort_values(by='_dt').drop(columns=['_dt'])
    rows = df_display.to_dict(orient='records') or [{"Beschreibung": "", "Aufgabe": "", "Datum": "", "Dauer": ""}]

    # Template laden und rendern
    with open(template_path, encoding="utf-8") as f:
        tpl = Template(f.read())

    rendered = tpl.render(
        client=client,
        project=project,
        months_range=months_range,
        logo=logo_url,
        rows=rows,
        total_hours=f"{total_hours:.2f}".replace(".", ",")
    )
    return rendered


def save_html_file(html_content: str, filename: str):
    """
    Speichert den gerenderten HTML-String als Datei.
    """
    with open(filename, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"✅ HTML-Datei gespeichert als {filename}")


def convert_html_to_pdf_and_cleanup(html_filename: str, csv_filename: str, df: pd.DataFrame, client: str, project: str, css_file: Path):
    """
    Konvertiert HTML in PDF mit korrektem Namen und löscht die HTML- und CSV-Datei.
    """
    # Monat und Jahr bestimmen aus den Daten
    first_date = pd.to_datetime(df["start"], dayfirst=True).sort_values().iloc[0]
    monat = f"{first_date.month:02d}"
    jahr  = f"{first_date.year}"

    # PDF-Dateiname bestimmen
    if project.strip().lower() in ("alle projekte", "alle"):
        pdf_filename = f"Stundenauflistung_{client}_{monat}_{jahr}.pdf"
    else:
        pdf_filename = f"Stundenauflistung_{client}_{project}_{monat}_{jahr}.pdf"

    # PDF erzeugen
    HTML(html_filename).write_pdf(
        pdf_filename,
        stylesheets=[CSS(str(css_file))]
    )
    print(f"✅ PDF wurde erstellt: {pdf_filename}")

    # HTML löschen
    try:
        os.remove(html_filename)
        print(f"🗑️ HTML-Datei {html_filename} wurde gelöscht")
    except Exception as e:
        print(f"⚠️ Fehler beim Löschen der HTML-Datei: {e}")

    # CSV löschen
    if csv_filename:
        try:
            os.remove(csv_filename)
            print(f"🗑️ CSV-Datei {csv_filename} wurde gelöscht")
        except Exception as e:
            print(f"⚠️ Fehler beim Löschen der CSV-Datei: {e}")



def get_months_range_string(df: pd.DataFrame) -> str:
    """
    Returns a string like:
       - 'Juni 2025'
       - 'Mai/Juni 2025'
       - 'Juni/Juli/August 2025'
       - 'Dezember 2024, Januar 2025'
    depending on the dates in the DataFrame.
    """

    # Try setting German locale for month names
    try:
        locale.setlocale(locale.LC_TIME, 'de_DE.UTF-8')
    except locale.Error:
        print("⚠️ Achtung: German locale not available – months will be in English.")

    if df.empty:
        return ""

    # Convert 'start' column to datetime, safely
    df["start_dt"] = pd.to_datetime(df["start"], format="%d.%m.%Y", errors="coerce")
    df = df.dropna(subset=["start_dt"])

    if df.empty:
        return ""

    # Extract year and month as Period
    df["year_month"] = df["start_dt"].dt.to_period("M")
    unique_periods = sorted(df["year_month"].unique())

    # Group months by year
    year_to_months = defaultdict(list)
    for p in unique_periods:
        year_to_months[p.year].append(p.month)

    def split_into_consecutive_blocks(months):
        months = sorted(set(months))
        if not months:
            return []
        blocks = []
        block = [months[0]]
        for m in months[1:]:
            if m - block[-1] == 1:
                block.append(m)
            else:
                blocks.append(block)
                block = [m]
        blocks.append(block)
        return blocks

    parts = []
    for year in sorted(year_to_months.keys()):
        months = sorted(set(year_to_months[year]))
        blocks = split_into_consecutive_blocks(months)

        block_parts = []
        for block in blocks:
            if len(block) > 1:
                month_names = [datetime(year, m, 1).strftime("%B") for m in block]
                block_parts.append("/".join(month_names) + f" {year}")
            else:
                month_name = datetime(year, block[0], 1).strftime("%B") + f" {year}"
                block_parts.append(month_name)

        parts.append(", ".join(block_parts))

    return ", ".join(parts)


def choose_period() -> tuple[str, str]:
    while True:
        raw_start = input("Start period (DD-MM or DD-MM-YYYY): ").strip()
        raw_end   = input("End   period (DD-MM or DD-MM-YYYY): ").strip()

        try:
            start_iso = to_iso_format(raw_start, is_end=False)
            end_iso   = to_iso_format(raw_end,   is_end=True)

            if start_iso > end_iso:
                print("❌ End date is before start date. Please try again.\n")
                continue

            print(f"✅ Selected period: {start_iso} … {end_iso}\n")
            return start_iso, end_iso

        except ValueError as e:
            print(f"❌ Invalid date: {e}. Please try again.\n")


def load_entries_for_period(start_iso: str, end_iso: str) -> pd.DataFrame:
    df_date = get_entries_by_date(start_iso, end_iso)
    print("DEBUG: rows after date filter:", len(df_date))
    return df_date


def process_reports_loop(df_date: pd.DataFrame, template_path: Path, logo_file: Path, css_file: Path):
    while True:
        # --- Список клиентов в выборке ---
        clients_in_period = sorted(df_date['client_name'].dropna().unique().tolist())
        print("DEBUG: clients in period:", clients_in_period)

        # --- Client filter ---
        df_client = filter_by_client_inter(df_date)
        print("DEBUG: rows after client filter:", len(df_client))

        # --- Список проектов для этого клиента ---
        projects_in_client = sorted(
            df_client.get('project_name', df_client.get('project.name', pd.Series()))
            .dropna().unique().tolist()
        )
        print("DEBUG: projects for client:", projects_in_client)

        # --- Project selection mit Enter für Alle ---
        project_choice = input("Project name (or just Enter for ALL): ").strip()

        if project_choice == "":
            # User wants ALL projects for this client
            df_proj = df_client.copy()
            project_name = "Alle Projekte"
            print(f"✅ Alle Projekte für Client werden genommen ({len(df_proj)} Einträge).")
        else:
            # User specified one project
            df_proj = filter_by_project(df_client, project_choice)
            if df_proj.empty:
                print(f"❌ No entries found for project '{project_choice}'. Please try again.\n")
                continue
            project_name = df_proj['project_name'].iloc[0]
            print(f"✅ Projekt gefiltert: {project_name} ({len(df_proj)} Einträge).")

        # --- CSV speichern ---
        client_name = df_proj['client_name'].iloc[0]
        csv_filename = f"report_{client_name}_{project_name}.csv"
        df_proj[['description', 'task_name', 'start', 'duration_hours']].to_csv(csv_filename, index=False)
        print(f"✅ Report for client “{client_name}”, project “{project_name}” saved as {csv_filename} ({len(df_proj)} rows)\n")

        # --- Monatsbereich berechnen ---
        df_proj['month_year'] = pd.to_datetime(df_proj['start'], dayfirst=True).dt.strftime('%B %Y')
        months_range = get_months_range_string(df_proj)

        # --- Total hours ---
        total_hours = df_proj['duration_hours'].sum()

        # --- 1) Render HTML ---
        rendered_html = render_report_html(
            df_proj,
            client_name,
            project_name,
            months_range,
            total_hours,
            template_path=template_path,
            logo_url=logo_file.as_uri()
        )

        # --- 2) Save HTML to file ---
        html_filename = f"report_{client_name}_{project_name}.html"
        save_html_file(rendered_html, html_filename)

        # --- 3) Convert to PDF and delete HTML ---
        convert_html_to_pdf_and_cleanup(
            html_filename=html_filename,
            csv_filename=csv_filename,
            df=df_proj,
            client=client_name,
            project=project_name,
            css_file=css_file
        )

        print(f"✅ Kompletter Report für {client_name} / {project_name} fertig!\n")

        # --- Continue? ---
        again = input("Generate a report for another client/project? (y/N): ").strip().lower()
        if again not in ('y', 'yes'):
            print("✅ Exiting.")
            break


if __name__ == "__main__":
    # --- Basis-Verzeichnisse ---
    BASE_DIR     = Path(__file__).resolve().parent
    TEMPLATE_DIR = BASE_DIR / "app" / "templates"
    STATIC_DIR   = BASE_DIR / "static"

    template_path = TEMPLATE_DIR / "report_template.html"
    logo_file     = STATIC_DIR / "Logo mit Slogan.png"
    css_file      = STATIC_DIR / "styles.css"

    # --- Check static assets ---
    if not logo_file.exists():
        raise FileNotFoundError(f"❌ Logo not found at path {logo_file}")
    if not css_file.exists():
        raise FileNotFoundError(f"❌ CSS file not found at path {css_file}")

    # --- Zeitraum wählen und Daten laden ---
    start_iso, end_iso = choose_period()
    df_date = load_entries_for_period(start_iso, end_iso)

    if df_date.empty:
        print("⚠️ Keine Daten im gewählten Zeitraum!")
        sys.exit(0)

    # --- Hauptloop für Reports ---
    process_reports_loop(df_date, template_path, logo_file, css_file)
