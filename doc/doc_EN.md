# Project Documentation "Clockify Report Generator"

## Introduction

This project enables the automatic creation of PDF reports based on time entries from the Clockify service. The web frontend is built with Streamlit, and the report generation uses ReportLab.

**Key Features:**

* User authentication via `secrets.toml` (for Streamlit) or `.env`
* Selection of date range and data retrieval via the Clockify API
* Interactive client and project selection
* Generation of tabular PDF reports with logo, header, and total hours

---

## Project Structure

```
ClockifyApp/
├── streamlit_app.py             # Web frontend (Streamlit)
├── main.py                      # Core logic: data fetching and processing
├── config.py                    # API key configuration and authentication
├── client_filters.py            # Client filtering and selection functions
├── auth_config.py               # Environment and Streamlit secrets setup
├── app_Flask/                   # Optional Flask templates
│   └── templates/
│       └── report_templates.html
├── static/                      # Static assets (logo, CSS)
│   ├── Logo mit Slogan.png
│   └── styles.css
├── requirements.txt             # Python dependencies
├── .streamlit/                  # Streamlit secrets directory
│   └── secrets.toml
├── .env                         # Environment variables for console mode
└── .gitignore
```

---

## Installation and Setup

1. **Clone the repository:**

   ```bash
   git clone https://.../ClockifyApp.git
   cd ClockifyApp
   ```
2. **Create a virtual environment:**

   ```bash
   python -m venv venv
   source venv/bin/activate   # Linux/Mac
   venv\\Scripts\\activate   # Windows
   ```
3. **Install dependencies:**

   ```bash
   pip install -r requirements.txt
   ```
4. **Configure environment variables:**

   * **Non-Streamlit (local):** Create a `.env` file containing:

     ```ini
     CLOCKIFY_API_KEY=<your_api_key>
     CLOCKIFY_WORKSPACE_ID=<your_workspace_id>
     CLOCKIFY_BASE_URL=https://api.clockify.me/api/v1  # default
     ```
   * **Streamlit:** Add the following to `secrets.toml`:

     ```toml
     [auth.admin]
     password_hash = "<sha256_hash>"

     [users.admin]
     api_key      = "<your_api_key>"
     workspace_id = "<your_workspace_id>"
     base_url     = "https://api.clockify.me/api/v1"
     ```

---

## Running the Application

* **Streamlit:**

  ```bash
  streamlit run streamlit_app.py
  ```

  Then open `http://localhost:8501` in your browser.

* **Console mode:**
  Import and use functions from `main.py` or `client_filters.py` directly in a Python REPL or script for debugging.

---

## Modules and Main Functions

### 1. `config.py`

* Detects whether the app is running under Streamlit (`IN_STREAMLIT`).
* Loads user credentials from `st.secrets["users"]` in Streamlit.
* Loads environment variables via `python-dotenv` in console mode.
* Constructs the shared `HEADERS` dictionary for Clockify API requests.

### 2. `main.py`

#### Functions:

* `to_iso_format(date_str: str, is_end=False) -> str`
  Converts various date string formats (e.g., "DD.MM.YYYY", "YYYY-MM-DD") into ISO 8601, setting start or end of the day.

* `fetch_all(endpoint: str, base_url: str, headers: dict, params: dict=None) -> list[dict]`
  Retrieves all records from a Clockify endpoint, handling pagination.

* `get_entries_by_date(start_iso, end_iso, api_key, workspace_id, base_url) -> pd.DataFrame`
  Returns a DataFrame with columns:

  ```
  description, user_name,
  client_id, client_name,
  project_id, project_name,
  task_name, start, duration_hours
  ```

  **Workflow:**

  1. Fetch master lists of `projects` and `clients`.
  2. Retrieve all workspace users.
  3. For each user, fetch their time entries for the period.
  4. Enrich entries with project and client names.
  5. Calculate duration in hours and format the date.

* `generate_report_pdf(...)`
  Creates a tabular PDF report with ReportLab:

  * Header with logo and company name.
  * Title showing the month range.
  * Table with columns "Description", "Task", "Date", "Duration".
  * Final summary row with total hours.

* `filter_by_client(df) -> pd.DataFrame`
  Filters the DataFrame by an exact client name (case-insensitive).

* `filter_by_client_inter(df) -> pd.DataFrame`
  Interactive selection (Streamlit `selectbox` or console `input()`):

  * Lists all clients present in the selected period.
  * Allows choosing by number or name.
  * Resolves ambiguities if one name maps to multiple client IDs.

### 3. `streamlit_app.py`

* **Authentication:** Login form, password hash check against `secrets.toml`.
* **UI Workflow:**

  1. Select date range (`date_input`).
  2. Click "Daten laden" to fetch entries from Clockify.
  3. Select client (`selectbox`) and projects (`multiselect`).
  4. Confirm selection and generate the PDF.
* **Report Generation:** Calls `generate_report_pdf_bytes()` from `main.py` and offers a download button.
* **Navigation:** Buttons for "New Period", "Another Client", and "Exit".

---

## Example Workflow

1. Run `streamlit run streamlit_app.py`.
2. Log in with your user account.
3. Choose a date range and click "Daten laden".
4. Select the desired client and projects, then click "Confirm Selection".
5. Click "📥 Download PDF" to obtain the report.

---

## Important Notes

* Client and project names are sourced **only** from entries within the chosen period.
* If no data is found, appropriate messages appear (e.g., "Keine Daten...", "Keine Clients...").
* Ensure correct date formatting (`dd.mm.YYYY`) in `get_entries_by_date` settings.

---

## Contact and Support

For questions or bug reports, please contact the Inpro Analytics GmbH development team.
