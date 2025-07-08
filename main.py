from collections import defaultdict
from dateutil import parser
from datetime import datetime
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


def get_all_entries(start_iso: str, end_iso: str) -> pd.DataFrame:

    users = fetch_all(f"/workspaces/{WORKSPACE_ID}/users")
    if not users:
        print("No users found in the workspace.")
        return pd.DataFrame()
    
    frames_per_user = []
    for user in users:
        endpoint = f"/workspaces/{WORKSPACE_ID}/user/{user['id']}/time-entries"
        entries = fetch_all(endpoint, params={"start": start_iso, "end": end_iso})
        if entries:
            df = pd.json_normalize(entries, sep='.')

            if 'task.name' not in df.columns:
                df['task.name'] = None
 
            df['task_name'] = df['task.name'].fillna('').astype(str)
            df['user_name'] = user['name']
            df['client_name'] = df['project.clientName']
            df['start'] = (pd.to_datetime(df['timeInterval.start']).dt.strftime('%Y-%m-%d %H:%M:%S'))
            df['duration_hours'] = (
                pd.to_datetime(df['timeInterval.end'])
            - pd.to_datetime(df['timeInterval.start'])
            ).dt.total_seconds() / 3600

            frames_per_user.append(df)
        
    if frames_per_user:
        result = pd.concat(frames_per_user, ignore_index=True)
    else:
        result = pd.DataFrame()   
      
    df_report = result[[
        "user_name",
        "description",
        "client_name",   
        "task_name",      
        "start",
        "duration_hours"
    ]]

    return df_report


def filter_by_client(df: pd.DataFrame, client_input: str) -> pd.DataFrame:
    """
    Filter the DataFrame by client name.
    """
    clients = fetch_all(f"/workspaces/{WORKSPACE_ID}/clients")

    if not clients:
        print("No clients found in the workspace.")
        return df

    name_map = defaultdict(list)
    for client in clients:
        key = client["name"].lower()
        name_map[key].append(client["id"])

    if client_input not in name_map:
        print(f"Client '{client_input}' not found.")
      
        for name in sorted(name_map):
            print("  ", name)
        sys.exit(1)

    
    return df[df['client_name'].str.lower() == client_input.lower()]    
    


if __name__ == "__main__":
    # 1) Read and parse the date range
    try:
        start_input = input("Start of period (e.g. DD-MM or DD-MM-YYYY): ").strip()
        end_input   = input("End of period   (e.g. DD-MM or DD-MM-YYYY): ").strip()
        start_iso = to_iso_format(start_input, is_end=False)
        end_iso   = to_iso_format(end_input,   is_end=True)
    except ValueError as e:
        print(f"Error parsing date: {e}")
        sys.exit(1)

    # 2) Fetch all entries in that period
    df_all = get_all_entries(start_iso, end_iso)
    print(f"Total entries in period: {len(df_all)}")

    # Покажем клиентов, у которых есть записи в этом периоде
    clients_in_period = df_all['client_name'].dropna().unique().tolist()
    print("Clients WITH entries in this period:")
    for name in sorted(clients_in_period):
        print("  ", name)

    # 3) Ask for the client name
    client_input = input("Client name (exact, case-insensitive): ").strip().lower()

    # 4) Filter by client
    df_client = filter_by_client(df_all, client_input)
    if df_client.empty:
        print(f"No entries found for client '{client_input}'.")
        sys.exit(1)

    # 5) Show and save the result
    print("\nEntries for client:\n")
    print(df_client.head().to_string(index=False))

    df_client.to_csv("client_entries.csv", index=False)
    df_client.to_json(
        "client_entries.json",
        orient='records',
        indent=2,
        force_ascii=False
    )
    print(f" {len(df_client)} entries saved to client_entries.csv / .json")
