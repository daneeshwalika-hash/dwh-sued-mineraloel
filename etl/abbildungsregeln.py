"""
etl/abbildungsregeln.py

Zweck      : Alle Abbildungsregeln (Mappings) und festen Werte der Bereinigung an EINER Stelle.
             Die Codeliste ist eine Vereinbarung: Sie steht fest, BEVOR geladen wird.
             Ein Wert, der hier nicht steht, ist "unbekannt" und wird nie still zu NaN
             (Bestellungen -> rejected, Stammdaten -> Abbruch, siehe etl/03_bereinige_quellen.py).
Eingabe    : keine (nur Konstanten)
Ausgabe    : Konstanten für etl/03_bereinige_quellen.py und tests/test_bereinigung.py
Anforderung: Q-04 jede Bereinigungsregel ist dokumentiert, Q-05 reproduzierbar
Bezug      : E-02, E-03, E-04, E-08, E-09, E-12, E-18, E-21, E-23, E-25, E-26;
             data_quality_issues Nr 3, 4, 5, 10, 23, 24, 27, 31, 36, 44, 45
Aufruf     : wird importiert, nicht direkt gestartet

Schlüssel der Mapping-Tabellen sind immer klein geschrieben, ohne Leerzeichen am Rand
und in Unicode-NFC. Die Funktion schluessel() in 03_bereinige_quellen.py bringt jeden
Quellwert in genau diese Form, bevor nachgeschlagen wird.
"""
import datetime as dt

# ------------------------------------------------------------------------
# Datum (E-02, E-03, E-25, Nr 29, Nr 31)
# ------------------------------------------------------------------------
# Jedes Format wird ausdrücklich erkannt (Regex) und mit SEINEM Format-Code gelesen.
# Kein format="mixed", kein dayfirst: pandas soll nicht raten.
DATUMSFORMATE = [
    (r"\d{4}-\d{2}-\d{2}",   "%Y-%m-%d"),   # ISO
    (r"\d{2}\.\d{2}\.\d{4}", "%d.%m.%Y"),   # deutsch
    (r"\d{2}\.\d{2}\.\d{2}", "%d.%m.%y"),   # deutsch, Jahr 2-stellig: 21-25 -> 2021-2025 (E-25)
    (r"\d{2}/\d{2}/\d{4}",   "%m/%d/%Y"),   # MM/DD/YYYY, aus den Daten belegt (E-02, E-25)
]

# Exportdatum der Quelle (Nr 31). Ein Bestelldatum danach liegt in der Zukunft und
# wird wie ein ungültiges Datum behandelt (E-03).
EXPORT_STICHTAG = dt.date(2026, 1, 5)

# ------------------------------------------------------------------------
# Schlüssel (Nr 34, Nr 36, E-04, E-21)
# ------------------------------------------------------------------------
# Kundennummer nach upper(): 'K' + 4 Ziffern (wie CHECK ck_dim_kunde_kunden_nr)
MUSTER_KUNDEN_NR = r"K\d{4}"
# Artikelnummer nach upper() und ohne Leerzeichen: 'A005' und 'A-005' -> 'A-005' (Nr 36)
MUSTER_ARTIKEL_NR = r"([A-Z])-?(\d{3})"
# Business Key der Zeile -1 in dim_kunde (E-04, E-21). Leere oder unbekannte
# Kundennummern bekommen diesen Wert, damit der SQL-Lookup die Zeile -1 findet (E-24).
KUNDEN_NR_UNBEKANNT = "UNBEKANNT"

# ------------------------------------------------------------------------
# Bestellungen
# ------------------------------------------------------------------------
# 9 Schreibweisen -> 4 Zahlungsarten (Nr 44, P8, Zuordnung aus explore/01_explore.py).
# Zielwerte = Werte in dwh.dim_zahlung (CHECK ck_dim_zahlung_zahlungsart).
ZAHLUNGSART = {
    "rechnung":         "Rechnung",
    "re":               "Rechnung",
    "lastschrift":      "Lastschrift",
    "sepa":             "Lastschrift",
    "sepa-lastschrift": "Lastschrift",
    "bar":              "Bar",
    "barzahlung":       "Bar",
    "vorkasse":         "Vorkasse",
}

# Lieferstatus: nur Groß-/Kleinschreibung uneinheitlich (Nr 45) -> lower().
# Erlaubt sind genau die 4 Werte aus dwh.dim_status (E-12, E-18).
LIEFERSTATUS = {"geliefert", "teilgeliefert", "offen", "storniert"}

# Leerer Rabatt = 0 % (E-08, Annahme bis zur Antwort auf O-07)
RABATT_WENN_LEER = "0"

# ------------------------------------------------------------------------
# Kunden und Kunden-Update
# ------------------------------------------------------------------------
# G/gewerbe -> Gewerbe, P/privat -> Privat (Nr 3)
KUNDENTYP = {
    "gewerbe": "Gewerbe",
    "g":       "Gewerbe",
    "privat":  "Privat",
    "p":       "Privat",
}

# Ort -> offizielle Schreibweise (Nr 4: Groß/klein und Leerzeichen, Nr 5: Abkürzungen).
# Die Abkürzungen sind dieselben wie ORT_ABK in explore/plz_pruefung.py.
# Zielnamen = Schreibweise, die in den Daten selbst korrekt vorkommt.
ORT = {
    "böblingen":           "Böblingen",
    "boeblingen":          "Böblingen",
    "dresden":             "Dresden",
    "esslingen am neckar": "Esslingen am Neckar",
    "esslingen a.n.":      "Esslingen am Neckar",
    "esslingen":           "Esslingen am Neckar",
    "gärtringen":          "Gärtringen",
    "gaertringen":         "Gärtringen",
    "herrenberg":          "Herrenberg",
    "leipzig":             "Leipzig",
    "ludwigsburg":         "Ludwigsburg",
    "pforzheim":           "Pforzheim",
    "sindelfingen":        "Sindelfingen",
    "stuttgart":           "Stuttgart",
    "stgt.":               "Stuttgart",
    "tübingen":            "Tübingen",
    "tuebingen":           "Tübingen",
    "ulm":                 "Ulm",
    "ulm/donau":           "Ulm",
}

# PLZ-Bereich (erste 2 Ziffern) -> Bundesland, aus den eigenen Daten belegt (E-26):
# In kunden.csv (151 Zeilen mit PLZ) gehört jeder Bereich zu genau einem Bundesland.
# Gilt nur für die aktuellen Daten; ob ein Bereich Landesgrenzen überschreitet
# (z. B. 89), ist nicht geprüft. Unbekannter Bereich -> Abbruch.
PLZ_BEREICH_BUNDESLAND = {
    "01": "Sachsen",
    "04": "Sachsen",
    "70": "Baden-Württemberg",
    "71": "Baden-Württemberg",
    "72": "Baden-Württemberg",
    "73": "Baden-Württemberg",
    "75": "Baden-Württemberg",
    "89": "Baden-Württemberg",
}

# Schreibweisen des Bundeslands in der Datei (Nr 10). Wird NUR zum Vergleich mit dem
# abgeleiteten Wert benutzt (Warnung bei Abweichung, Nr 46), nie übernommen (E-09).
BUNDESLAND_DATEI = {
    "baden-württemberg":  "Baden-Württemberg",
    "baden-wuerttemberg": "Baden-Württemberg",
    "bw":                 "Baden-Württemberg",
    "sachsen":            "Sachsen",
}

# Spalten, die nicht ins DWH gehen (R-03 DSGVO; dim_kunde hat keine Straße)
KUNDEN_SPALTEN_NICHT_UEBERNEHMEN = ["strasse", "telefon", "email"]

# ------------------------------------------------------------------------
# Produkte
# ------------------------------------------------------------------------
# Einheit (Nr 23). Zielwerte L / Stück / kg wie in der Prüfung in explore/01_explore.py.
EINHEIT = {
    "l":         "L",
    "ltr":       "L",
    "liter":     "L",
    "stück":     "Stück",
    "stk":       "Stück",
    "pcs":       "Stück",
    "kg":        "kg",
    "kilogramm": "kg",
}

# aktiv (Nr 24): In den Daten kommen nur 1 / true / ja vor. Für "falsch" gibt es
# keinen belegten Wert, deshalb steht hier keiner (nicht erfinden). Ein anderer
# Wert ist unbekannt -> Abbruch.
AKTIV = {
    "1":    True,
    "true": True,
    "ja":   True,
}

# Land des Lieferanten -> ISO-Code (Nr 27, CHECK ck_dim_produkt_land)
LIEFERANT_LAND = {
    "de":          "DE",
    "deutschland": "DE",
    "germany":     "DE",
}

# Fehlender Lieferant (Nr 26): gleicher Text wie bei der Zeile -1 (E-23, E-21)
LIEFERANT_UNBEKANNT = "Unbekannt"
