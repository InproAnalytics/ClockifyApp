# Projektdokumentation „Clockify Report Generator"

## Einleitung

Das Projekt ermöglicht die automatische Erstellung von PDF‑Berichten basierend auf Zeiteinträgen aus dem Clockify‑Dienst. Das Web‑Frontend ist in Streamlit realisiert, die Berichtsgenerierung erfolgt mit ReportLab.

**Hauptfunktionen:**

* Authentifizierung der Benutzer über `secrets.toml` (für Streamlit) oder `.env`
* Auswahl des Zeitraums und Laden von Daten über die Clockify‑API
* Interaktive Auswahl von Kunden und Projekten
* Generierung tabellarischer PDF‑Berichte mit Logo, Überschrift und Stundensumme

---

## Projektstruktur

```
ClockifyApp/
├── streamlit_app.py             # Web‑Frontend (Streamlit)
├── main.py                      # Kernlogik: Datenabruf und -aufbereitung
├── config.py                    # API‑Schlüssel‑Konfiguration und Authentifizierung
├── client_filters.py            # Filter‑ und Auswahlfunktionen für Kunden
├── auth_config.py               # Environment‑ und Streamlit‑Secrets‑Konfiguration
├── app_Flask/                   # Optionale Flask‑Vorlagen
│   └── templates/
│       └── report_templates.html
├── static/                      # Statische Dateien (Logo, CSS)
│   ├── Logo mit Slogan.png
│   └── styles.css
├── requirements.txt             # Python‑Abhängigkeiten
├── .streamlit/                  # Streamlit‑Secrets
│   └── secrets.toml
├── .env                         # Environment‑Variablen für Konsolenmodus
└── .gitignore
```

---

## Installation und Einrichtung

1. **Repository klonen:**

   ```bash
   git clone https://.../ClockifyApp.git
   cd ClockifyApp
   ```
2. **Virtuelle Umgebung erstellen:**

   ```bash
   python -m venv venv
   source venv/bin/activate   # Linux/Mac
   venv\\Scripts\\activate   # Windows
   ```
3. **Abhängigkeiten installieren:**

   ```bash
   pip install -r requirements.txt
   ```
4. **Umgebungsvariablen konfigurieren:**

   * **Nicht‑Streamlit (lokal):** Erstelle eine `.env` mit:

     ```ini
     CLOCKIFY_API_KEY=<dein_api_key>
     CLOCKIFY_WORKSPACE_ID=<dein_workspace_id>
     CLOCKIFY_BASE_URL=https://api.clockify.me/api/v1  # Standard
     ```
   * **Streamlit:** Trage in `secrets.toml` ein:

     ```toml
     [auth.admin]
     password_hash = "<sha256_hash>"

     [users.admin]
     api_key      = "<dein_api_key>"
     workspace_id = "<dein_workspace_id>"
     base_url     = "https://api.clockify.me/api/v1"
     ```

---

## Anwendung starten

* **Streamlit:**

  ```bash
  streamlit run streamlit_app.py
  ```

  Öffne anschließend im Browser `http://localhost:8501`.

* **Konsolenmodus:**
  Importiere und nutze die Funktionen aus `main.py` oder `client_filters.py` direkt in einer Python‑Shell.

---

## Module und Kernfunktionen

### 1. `config.py`

* Erkennt, ob die Anwendung in Streamlit läuft (`IN_STREAMLIT`).
* Lädt in Streamlit Benutzerdaten aus `st.secrets["users"]`.
* Lädt im Konsolenmodus Umgebungsvariablen via `python-dotenv`.
* Erstellt das gemeinsame `HEADERS`‑Dictionary für Clockify‑API‑Anfragen.

### 2. `main.py`

#### Funktionen:

* `to_iso_format(date_str: str, is_end=False) -> str`
  Wandelt Datumsangaben (z. B. "DD.MM.YYYY", "YYYY-MM-DD") in ISO 8601 um und setzt Anfang bzw. Ende des Tages.

* `fetch_all(endpoint: str, base_url: str, headers: dict, params: dict=None) -> list[dict]`
  Lädt seitenweise alle Datensätze von einem Clockify‑Endpoint.

* `get_entries_by_date(start_iso, end_iso, api_key, workspace_id, base_url) -> pd.DataFrame`
  Gibt ein DataFrame zurück mit folgenden Spalten:

  ```
  description, user_name,
  client_id, client_name,
  project_id, project_name,
  task_name, start, duration_hours
  ```

  **Workflow:**

  1. Abruf der Master‑Listen `projects` und `clients`.
  2. Abruf aller Workspace‑Benutzer.
  3. Für jeden Benutzer: Abruf der Time‑Entries im Zeitraum.
  4. Anreicherung der Einträge mit Projekt‑ und Kundennamen.
  5. Berechnung der Stunden und Formatierung des Datums.

* `generate_report_pdf(...)`
  Erzeugt einen tabellarischen PDF‑Bericht mit ReportLab:

  * Kopfzeile mit Logo und Firmenname.
  * Titel mit dem gewählten Monatsbereich.
  * Tabelle mit den Spalten „Beschreibung“, „Aufgabe“, „Datum“, „Dauer“.
  * Abschließende Summenzeile mit Gesamtstunden.

* `filter_by_client(df) -> pd.DataFrame`
  Filtert das DataFrame nach einem exakten Kundennamen (case‑insensitive).

* `filter_by_client_inter(df) -> pd.DataFrame`
  Interaktive Auswahl (Streamlit `selectbox` oder Konsolen‑`input()`):

  * Listet alle Kunden im gewählten Zeitraum auf.
  * Ermöglicht die Auswahl per Name oder Nummer.
  * Klärt Mehrdeutigkeiten, falls ein Name mehreren IDs zugeordnet ist.

### 3. `streamlit_app.py`

* **Authentifizierung:** Login/Passwort‑Abfrage, Prüfung gegen `secrets.toml`.
* **UI‑Workflow:**

  1. Zeitraum wählen (`date_input`).
  2. „Daten laden“ – Abruf aus Clockify.
  3. Kunde (`selectbox`) und Projekte (`multiselect`) auswählen.
  4. Auswahl bestätigen und PDF generieren.
* **Berichtsgenerierung:** Ruft `generate_report_pdf_bytes()` auf und bietet den Download an.
* **Navigation:** Buttons „Neuer Zeitraum“, „Anderer Client“, „Beenden“.

---

## Beispielhafter Ablauf

1. `streamlit run streamlit_app.py`
2. Anmelden mit Benutzerkonto.
3. Zeitraum auswählen und „Daten laden“ klicken.
4. Kunde und Projekte wählen, „Auswahl bestätigen“.
5. „📥 PDF herunterladen“ – der Bericht steht zum Download bereit.

---

## Wichtige Hinweise

* Kunden‑ und Projekt­namen stammen **ausschließlich** aus Einträgen im gewählten Zeitraum.
* Bei fehlenden Daten erscheinen Hinweise wie „Keine Daten…“ oder „Keine Clients…“.
* Für korrektes Datumsformat (`dd.mm.YYYY`) muss `get_entries_by_date` entsprechend konfiguriert sein.

---

## Kontakt und Support

Bei Fragen und Bugreports wende dich bitte an das Entwicklungsteam der Inpro Analytics GmbH.
