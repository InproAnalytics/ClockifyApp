from collections import defaultdict
from datetime import datetime
from dateutil import parser
import pandas as pd
import requests
import sys


API_KEY      = 'ZTlkNGRlNzQtZDBkMy00NDY0LWEyZTQtMzdhZTQ0YjlmOWM4'
WORKSPACE_ID = '66052c545402842181578e74'
BASE_URL     = "https://api.clockify.me/api/v1"
HEADERS      = {'X-Api-Key': API_KEY, 'Content-Type': 'application/json'}


def to_iso_format(date_str: str, is_end=False) -> str:
    """
    Parse a human-friendly date string into ISO-8601 with trailing 'Z'.
    If no time is present, uses 00:00:00 (is_end=False) or 23:59:59 (is_end=True).
    """
    try:
        # dayfirst=True: "01-06" → 1st of June
        dt = parser.parse(date_str, dayfirst=True, default=datetime.now())
    except (ValueError, OverflowError) as e:
        raise ValueError(f"Could not parse date '{date_str}': {e}")

    # If the user didn’t include a time component, set day boundaries:
    if ":" not in date_str:
        dt = dt.replace(hour=23, minute=59, second=59) if is_end else dt.replace(hour=0, minute=0, second=0)

    return dt.replace(microsecond=0).isoformat() + "Z"


def fetch_all(endpoint: str, params: dict = None) -> list:
    """Fetch all pages (handle pagination) from the Clockify API."""
    items = []
    page = 1
    while True:
        q = {"page-size": 1000, "page": page, "hydrated": "true"}
        if params:
            q.update(params)

        resp = requests.get(
            f"{BASE_URL}{endpoint}",
            headers=HEADERS,
            params=q
        )
        resp.raise_for_status()
        batch = resp.json()
        if not batch:
            break
        items.extend(batch)
        page += 1

    return (items)


def get_entries_by_date(start_iso: str, end_iso: str) -> pd.DataFrame:
    """Return a DataFrame of all time entries for the specified date range."""
    users = fetch_all(f"/workspaces/{WORKSPACE_ID}/users")
    if not users:
        print("No users found in the workspace.")
        return pd.DataFrame()
    
    frames = []
    for user in users:
        entries = fetch_all(
            f"/workspaces/{WORKSPACE_ID}/user/{user['id']}/time-entries",
            params={"start": start_iso, "end": end_iso}
        )
        if not entries:
            continue
        df = pd.json_normalize(entries, sep='.')

        df['client_id'] = (
            df.get('project.clientId', pd.Series([None] * len(df)))
              .fillna('')
              .astype(str)
        )
        df['project_name'] = (
            df.get('project.name', pd.Series([''] * len(df)))
              .fillna('')
              .astype(str)
        )
        df['user_name']   = user['name']
        df['client_name'] = df.get('project.clientName', pd.Series(['']*len(df))).fillna('').astype(str)
        df['project_id']  = df.get('projectId', pd.Series([None]*len(df)))
        df['task_name']   = df.get('task.name', pd.Series(['']*len(df))).fillna('').astype(str)
        df['start']       = pd.to_datetime(df['timeInterval.start']).dt.strftime('%Y-%m-%d %H:%M:%S')
        df['duration_hours'] = (
            pd.to_datetime(df['timeInterval.end']) -
            pd.to_datetime(df['timeInterval.start'])
        ).dt.total_seconds() / 3600
        frames.append(df)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def filter_by_client(df: pd.DataFrame, client_name: str) -> tuple[pd.DataFrame, str]:
    """Filter entries by client name (case-insensitive)."""
    key = client_name.lower().strip()

    clients = fetch_all(f"/workspaces/{WORKSPACE_ID}/clients")

    name_map = defaultdict(list) 
    for c in clients:
        name_map[c['name'].lower()].append(c['id']) 
    if key not in name_map:
        print(f"Client '{client_name}' not found.")
        print("Available clients:")
        for n in sorted(name_map):
            print("  ", n)
        sys.exit(1)
    if len(name_map[key]) > 1:
        print(f"Multiple clients named '{client_name}': {name_map[key]}")
        sys.exit(1)
    client_id = name_map[key][0]
    df_client = df[
        (df['client_name'].str.lower() == key) &
        (df['client_id']   == client_id)
    ].copy()
    return df_client, client_id


def filter_by_project(df: pd.DataFrame, project_name: str)-> pd.DataFrame:
    """Filter entries by project name (case-insensitive)."""
    key = project_name.lower().strip()
    
    available = df['project_name'].str.lower().unique().tolist()

    if key not in available:
        print(f"Project '{project_name}' not found.")
        print("Available projects for this client:")
        for name in sorted(available):
            print("  ", name)
        sys.exit(1)
    
    # Фильтруем DataFrame по точному совпадению project_name
    mask = df['project_name'].str.lower() == key
    return df[mask].copy()


def get_data(client: str, project: str, start: str, end: str) -> pd.DataFrame:
    """Fetch and filter time entries based on client, project, and date range."""
    start_iso = to_iso_format(start, is_end=False)
    end_iso   = to_iso_format(end,   is_end=True)
    print("DEBUG: start_iso =", start_iso, " end_iso =", end_iso)

    df_date   = get_entries_by_date(start_iso, end_iso)
    print("DEBUG: entries by date — rows:", len(df_date))
    print(df_date[['user_name','start','project_id']].head())
    print("DEBUG: unique client names in df_date:", sorted(df_date['client_name'].dropna().unique().tolist()))

    df_client = filter_by_client(df_date, client)
    df_proj   = filter_by_project(df_client, project)
    return df_proj


if __name__ == "__main__":
    # 1)
    start = input("Start period (DD-MM or DD-MM-YYYY): ").strip()
    end   = input("End   period (DD-MM or DD-MM-YYYY): ").strip()

    try:
        start_iso = to_iso_format(start, is_end=False)
        end_iso   = to_iso_format(end,   is_end=True)
    except ValueError as e:
        print("❌ Error parsing dates:", e)
        sys.exit(1)

    print(f"DEBUG: start_iso={start_iso}, end_iso={end_iso}")

    # 2)
    df_date = get_entries_by_date(start_iso, end_iso)
    print("DEBUG: rows after date filter:", len(df_date))
    if not df_date.empty:
        print(df_date[['user_name', 'start', 'project_id']].head().to_string(index=False))

    # 3) Список клиентов в выборке
    clients_in_period = sorted(df_date['client_name'].dropna().unique().tolist())
    print("DEBUG: clients in period:", clients_in_period)

    # 4) Ввод клиента и фильтрация
    client = input("Client name (exact): ").strip()
    df_client, client_id = filter_by_client(df_date, client)
    print("DEBUG: rows after client filter:", len(df_client))
    if not df_client.empty:
        print(df_client[['client_name', 'project_id']].head().to_string(index=False))

    # 5) Список проектов в выборке клиента
    projects_in_client = sorted(df_client.get('project_name', df_client.get('project.name', pd.Series())).dropna().unique().tolist())
    print("DEBUG: projects for client:", projects_in_client)

    # 6) Ввод проекта и фильтрация
    project = input("Project name (exact): ").strip()
    df_proj = filter_by_project(df_client, project)
    print("DEBUG: rows after project filter:", len(df_proj))
    if not df_proj.empty:
        print(df_proj[['description', 'task_name', 'start', 'duration_hours']].head().to_string(index=False))

    # 7) Сохранение итогового отчёта
    if df_proj.empty:
        print("No final entries to save.")
    else:
        df_proj[['description', 'task_name', 'start', 'duration_hours']].to_csv("report.csv", index=False)
        print(f"\n✅ Final report saved, {len(df_proj)} rows.")
