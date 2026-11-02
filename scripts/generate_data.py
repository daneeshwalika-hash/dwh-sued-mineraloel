"""Generate the synthetic raw data for the DWH Süd-Mineralöl project.

Fictional company: Süd-Mineralöl Handel GmbH (wholesale fuels & lubricants, Baden-Württemberg).
All names, addresses, phone numbers and e-mail addresses are fictional.
The data is deliberately "dirty" (mixed formats, duplicates, orphans, invalid values) so that
the ETL pipeline has real data quality problems to detect, correct or reject.

Seed 42 makes every run identical: the output is byte-identical to the files in data/raw/.

Usage (from the project folder):
    python scripts/generate_data.py                  # writes to data/generated/
    python scripts/generate_data.py --out some/dir   # writes to another folder
data/raw/ is never overwritten by default (the raw files must stay unchanged).
"""
import argparse
import csv
import json
import random
from datetime import date, timedelta
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser(description="Generate the synthetic raw data (seed 42).")
parser.add_argument("--out", type=Path, default=PROJECT / "data" / "generated",
                    help="output folder (default: data/generated/)")
OUT = parser.parse_args().out
OUT.mkdir(parents=True, exist_ok=True)

random.seed(42)

# ---------------- Customers ----------------
cities = [
    ("70173", "Stuttgart", ["Stuttgart", "stuttgart", " Stuttgart ", "STUTTGART", "Stgt."]),
    ("71032", "Böblingen", ["Böblingen", "Boeblingen", "böblingen", "Böblingen "]),
    ("71065", "Sindelfingen", ["Sindelfingen", "sindelfingen", "Sindelfingen "]),
    ("71116", "Gärtringen", ["Gärtringen", "Gaertringen", "gärtringen"]),
    ("72070", "Tübingen", ["Tübingen", "Tuebingen", "TÜBINGEN"]),
    ("71083", "Herrenberg", ["Herrenberg", "herrenberg"]),
    ("73728", "Esslingen am Neckar", ["Esslingen am Neckar", "Esslingen a.N.", "Esslingen"]),
    ("71638", "Ludwigsburg", ["Ludwigsburg", "ludwigsburg", "Ludwigsburg "]),
    ("75172", "Pforzheim", ["Pforzheim", "PFORZHEIM"]),
    ("89073", "Ulm", ["Ulm", "ulm", "Ulm/Donau"]),
    ("01067", "Dresden", ["Dresden"]),          # leading-zero PLZ trap
    ("04109", "Leipzig", ["Leipzig", "leipzig"]),  # leading-zero PLZ trap
]
bundesland = {"Dresden": "Sachsen", "Leipzig": "Sachsen"}

first = ["Thomas", "Andreas", "Stefan", "Michael", "Sabine", "Petra", "Julia", "Markus", "Katrin",
         "Frank", "Anna", "Jürgen", "Monika", "Ahmad", "Elif", "Lukas", "Sophie", "Daniel", "Nina", "Uwe"]
last = ["Müller", "Schmidt", "Schneider", "Fischer", "Weber", "Meyer", "Wagner", "Becker", "Schulz",
        "Hoffmann", "Koch", "Richter", "Klein", "Wolf", "Schröder", "Neumann", "Yilmaz", "Braun", "Krüger", "Hofmann"]
firm_types = ["Spedition", "Autohaus", "Landwirtschaft", "Bau GmbH", "Heizungsbau", "Transporte", "Werkstatt", "Logistik"]
streets = ["Hauptstraße", "Bahnhofstraße", "Industriestraße", "Gartenstraße", "Schillerstraße", "Daimlerstraße", "Robert-Bosch-Str."]

def messy_phone():
    n = f"{random.randint(7000,7999)}{random.randint(100000,999999)}"
    fmt = random.choice(["0{a} {b}", "+49 {a} {b}", "0{a}/{b}", "0049{a}{b}", "0{a}-{b}"])
    return fmt.format(a=n[:4], b=n[4:])

def messy_date(d):
    return random.choices(
        [d.isoformat(), d.strftime("%d.%m.%Y"), d.strftime("%m/%d/%Y"), d.strftime("%d.%m.%y")],
        weights=[55, 30, 10, 5])[0]

customers = []
for i in range(1, 151):
    fn, ln = random.choice(first), random.choice(last)
    plz, city_clean, variants = random.choice(cities)
    ktyp = random.choices(["Gewerbe", "Privat"], weights=[70, 30])[0]
    firma = f"{ln} {random.choice(firm_types)}" if ktyp == "Gewerbe" else ""
    email = f"{fn.lower()}.{ln.lower()}@{random.choice(['web.de','gmx.de','t-online.de','firma-bw.de'])}"
    email = email.replace("ü", "ue").replace("ö", "oe").replace("ä", "ae")
    r = random.random()
    if r < 0.08: email = ""
    elif r < 0.12: email = email.replace("@", "")            # invalid
    elif r < 0.15: email = email.split(".de")[0]              # missing TLD
    elif r < 0.20: email = email.upper()
    plz_out = plz
    r = random.random()
    if plz.startswith("0") and r < 0.7: plz_out = plz.lstrip("0")  # lost leading zero
    elif r < 0.08: plz_out = "D-" + plz
    elif r < 0.12: plz_out = plz + " "
    elif r < 0.14: plz_out = ""
    created = date(2021, 1, 1) + timedelta(days=random.randint(0, 1400))
    customers.append({
        "kunden_nr": f"K{i:04d}",
        "kundentyp": random.choice([ktyp, ktyp, ktyp.lower(), ktyp[0]]),
        "firma": firma,
        "vorname": fn if random.random() > 0.03 else "",
        "nachname": ln if random.random() > 0.05 else ln.upper(),
        "strasse": f"{random.choice(streets)} {random.randint(1,120)}",
        "plz": plz_out,
        "ort": random.choice(variants),
        "bundesland": bundesland.get(city_clean, random.choice(["Baden-Württemberg", "Baden-Württemberg", "BW", "Baden-Wuerttemberg"])),
        "telefon": messy_phone() if random.random() > 0.1 else "",
        "email": email,
        "erstellt_am": messy_date(created),
    })

# exact duplicates + near duplicates (same person, new kunden_nr)
for c in random.sample(customers, 4):
    customers.append(dict(c))
for n, c in enumerate(random.sample(customers[:150], 3)):
    d = dict(c); d["kunden_nr"] = f"K{151+n:04d}"; d["telefon"] = messy_phone()
    d["ort"] = d["ort"].strip().lower()
    customers.append(d)
random.shuffle(customers)

with open(OUT / "kunden.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(customers[0].keys()), delimiter=";")
    w.writeheader(); w.writerows(customers)

# ---------------- Products (JSON, nested) ----------------
prod_defs = [
    ("Kraftstoffe", "Diesel B7", "L", 1.62), ("Kraftstoffe", "Super E10", "L", 1.74),
    ("Kraftstoffe", "Super E5", "L", 1.80), ("Kraftstoffe", "HVO100 Diesel", "L", 1.85),
    ("Heizöl", "Heizöl EL schwefelarm", "L", 1.05), ("Heizöl", "Heizöl Premium", "L", 1.12),
    ("Motoröle", "Motoröl 5W-30 Longlife", "L", 9.90), ("Motoröle", "Motoröl 10W-40", "L", 7.50),
    ("Motoröle", "Motoröl 0W-20", "L", 12.40), ("Motoröle", "Motoröl 15W-40 LKW", "L", 6.80),
    ("Hydrauliköle", "Hydrauliköl HLP 46", "L", 4.20), ("Hydrauliköle", "Hydrauliköl HLP 68", "L", 4.35),
    ("Getriebeöle", "Getriebeöl 75W-90", "L", 11.20), ("Getriebeöle", "ATF Dexron III", "L", 8.10),
    ("Additive", "AdBlue", "L", 0.89), ("Additive", "Kühlerfrostschutz G12", "L", 3.90),
    ("Additive", "Diesel-Fließverbesserer", "L", 14.50), ("Schmierfette", "Mehrzweckfett Lithium", "kg", 8.70),
    ("Schmierfette", "Hochtemperaturfett", "kg", 15.30), ("Zubehör", "Ölwanne 20L", "Stk", 12.99),
    ("Zubehör", "Einfüllpistole", "Stk", 24.50), ("Zubehör", "Kanister 20L Metall", "Stk", 29.90),
    ("Zubehör", "Ölbindemittel Sack 20kg", "Stk", 18.40), ("Zubehör", "Handpumpe Fass", "Stk", 89.00),
]
unit_variants = {"L": ["L", "l", "Liter", "ltr"], "kg": ["kg", "KG", "Kilogramm"], "Stk": ["Stk", "Stück", "stk", "pcs"]}
products = []
for i, (cat, name, unit, price) in enumerate(prod_defs, 1):
    p = {
        "artikel_nr": f"A-{i:03d}",
        "bezeichnung": name if random.random() > 0.1 else name.upper(),
        "kategorie": {"haupt": cat, "unter": name.split()[0]},
        "einheit": random.choice(unit_variants[unit]),
        "preis": random.choice([price, f"{price:.2f}".replace(".", ",") + " €", f"{price:.2f}"]),
        "lieferant": {"name": random.choice(["Aral AG", "Shell Deutschland", "Castrol", "Liqui Moly", "Fuchs Schmierstoffe", "Mannol"]),
                      "land": random.choice(["DE", "DE", "Deutschland", "Germany"])},
        "aktiv": random.choice([True, True, True, "ja", 1]),
    }
    if random.random() < 0.1: p["preis"] = None
    if random.random() < 0.1: del p["lieferant"]
    products.append(p)
# a duplicate product with different spacing in artikel_nr
dup = dict(products[6]); dup["artikel_nr"] = "a-007 "; products.append(dup)

with open(OUT / "produkte.json", "w", newline="\n", encoding="utf-8") as f:
    json.dump({"export_datum": "2026-01-05", "quelle": "WaWi-Export", "artikel": products}, f, ensure_ascii=False, indent=2)

# ---------------- Orders (flat order lines) ----------------
zahlungsarten = ["Rechnung", "rechnung", "RE", "Lastschrift", "SEPA-Lastschrift", "SEPA", "Barzahlung", "bar", "Vorkasse"]
status = ["geliefert", "Geliefert", "GELIEFERT", "offen", "storniert", "teilgeliefert"]
valid_k = [f"K{i:04d}" for i in range(1, 151)]
base_price = {f"A-{i:03d}": pr for i, (_, _, _, pr) in enumerate(prod_defs, 1)}

rows = []
bnr = 100000
start = date(2024, 1, 1)
for _ in range(700):
    bnr += random.randint(1, 3)
    d = start + timedelta(days=random.randint(0, 730))
    k = random.choice(valid_k)
    r = random.random()
    if r < 0.02: k = ""
    elif r < 0.04: k = "K9999"          # orphan
    elif r < 0.07: k = k.lower()
    za = random.choice(zahlungsarten)
    for pos in range(1, random.randint(1, 5) + 1):
        art = random.choice(list(base_price))
        is_fuel = int(art[2:]) <= 6
        menge = random.choice([500, 1000, 1500, 2000, 3000, 5000]) if is_fuel else random.randint(1, 60)
        rr = random.random()
        if rr < 0.02: menge = -menge            # return or error
        elif rr < 0.03: menge = 0
        preis = round(base_price[art] * random.uniform(0.95, 1.08), 2)
        preis_s = f"{preis:.2f}".replace(".", ",")
        if random.random() < 0.03: preis_s = ""
        art_out = art if random.random() > 0.05 else random.choice([art.lower(), art + " ", art.replace("-", "")])
        if random.random() < 0.005: art_out = "A-999"   # unknown product
        rows.append({
            "bestell_nr": bnr, "position": pos, "bestelldatum": messy_date(d),
            "kunden_nr": k, "artikel_nr": art_out, "menge": menge, "einzelpreis": preis_s,
            "rabatt_prozent": random.choice(["0", "0", "0", "5", "10", "2,5", ""]),
            "zahlungsart": za, "lieferstatus": random.choice(status),
        })
# future dates + exact duplicate lines
for r_ in random.sample(rows, 3):
    r_["bestelldatum"] = "2027-02-30" if random.random() < 0.5 else "15.08.2027"
rows += [dict(r) for r in random.sample(rows, 25)]
random.shuffle(rows)

with open(OUT / "bestellungen.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys()), delimiter=";")
    w.writeheader(); w.writerows(rows)

# ---------------- Customer delta extract (for SCD Type 2) ----------------
clean_by_nr = {c["kunden_nr"]: c for c in customers}
delta = []
for nr in random.sample(valid_k, 15):
    c = dict(clean_by_nr[nr])
    plz, city_clean, _ = random.choice(cities)
    c["plz"], c["ort"] = plz, city_clean       # customer moved
    if random.random() < 0.4: c["telefon"] = messy_phone()
    if random.random() < 0.3: c["kundentyp"] = "Gewerbe"
    delta.append(c)
for i in range(160, 165):                        # new customers
    fn, ln = random.choice(first), random.choice(last)
    plz, city_clean, _ = random.choice(cities)
    delta.append({"kunden_nr": f"K{i:04d}", "kundentyp": "Gewerbe", "firma": f"{ln} {random.choice(firm_types)}",
                  "vorname": fn, "nachname": ln, "strasse": f"{random.choice(streets)} {random.randint(1,120)}",
                  "plz": plz, "ort": city_clean, "bundesland": bundesland.get(city_clean, "Baden-Württemberg"),
                  "telefon": messy_phone(), "email": f"info@{ln.lower()}-gmbh.de", "erstellt_am": "2026-01-10"})
with open(OUT / "kunden_update_2026-01.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(delta[0].keys()), delimiter=";")
    w.writeheader(); w.writerows(delta)

print("customers", len(customers), "products", len(products), "order lines", len(rows), "delta", len(delta))
print("written to", OUT)
