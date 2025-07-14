# Recherche: HTML-zu-PDF-Konvertierung in Python

## Ziel

Geeignete Bibliotheken vergleichen, um ein HTML-Template in einen PDF-Bericht umzuwandeln.
- Logo, 
- Überschriften: h1 und h2 
- Tabelle bis ca. 3 Seiten

---

## Untersuchte Optionen

### 1. WeasyPrint

**Beschreibung:** reine Python-Bibliothek für HTML+CSS → PDF.
**Vorteile:**

* Einfache Installation
* Gute CSS-Druckunterstützung
* Ideal für mehrseitige Tabellenberichte
* `@page`, Kopf-/Fußzeilen-Unterstützung
* Keine externen Binärdateien erforderlich

**Nachteile:**

* Führt kein JavaScript aus
* CSS muss sauber gepflegt sein

**Fazit:** bester Kandidat für unseren strukturierten HTML-Report ohne JS.

---

### 2. pdfkit (wkhtmltopdf)

**Beschreibung:** Wrapper um wkhtmltopdf.
**Vorteile:**

* Unterstützt JavaScript
* Sehr präzises Rendering
* Weit verbreitet

**Nachteile:**

* Externe wkhtmltopdf-Installation nötig
* Weniger flexibel bei Stiloptionen
* Zugriff auf lokale Dateien muss konfiguriert werden

**Fazit:** gut für komplexes HTML mit JS, aber überdimensioniert für unseren Fall.

---

### 3. xhtml2pdf

**Beschreibung:** reine Python-Lösung für (X)HTML → PDF.
**Vorteile:**

* Sehr leichtgewichtig
* Keine externen Abhängigkeiten

**Nachteile:**

* Begrenzte CSS-Unterstützung
* Für komplexe Layouts ungeeignet

**Fazit:** nur für sehr einfache Reports brauchbar.

---

### 4. ReportLab

**Beschreibung:** PDF-Erstellung komplett in Python.
**Vorteile:**

* Vollständige Layout-Kontrolle
* Diagramme, Tabellen, dynamische Inhalte

**Nachteile:**

* Kein direktes HTML-Parsing
* Hoher manueller Aufwand

**Fazit:** nicht geeignet für unser fertiges HTML-Template.

---

### 5. Pyppeteer / Playwright

**Beschreibung:** Browser-gesteuertes Rendering (Chromium).
**Vorteile:**

* Volle JS-Unterstützung
* Exaktes Browser-Rendering

**Nachteile:**

* Schwergewichtiger Stack
* Langsamer und ressourcenintensiver

**Fazit:** übertrieben für unser einfaches statisches Template.

---

## 📌 Endauswahl

✅ Unser HTML ist **einfach aufgebaut** und ohne JavaScript. Es soll als Druckbericht mit Logo und Tabelle (bis 3 Seiten) sauber ausgegeben werden.

**→ WeasyPrint ist die optimale Wahl.**

* Saubere Python-Integration
* Einfach über CSS zu steuern
* Sehr gute Unterstützung für mehrseitige Tabellenberichte
* Keine zusätzlichen Binärabhängigkeiten
