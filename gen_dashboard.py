"""
Regeneration du dashboard_achats.html avec donnees fraiches de la DB.
Strategie : injection en variable JS directe (var D={...}) — evite JSON.parse().
Le main script contient "var D=JSON.parse(...)" que l'on remplace par "/* D injected */".
"""
import sys, os, logging, json, re
from datetime import datetime

os.chdir(r'C:\Users\abezille\dev\Data-Achat')
sys.path.insert(0, '.')
logging.getLogger('azure.core.pipeline').setLevel(logging.WARNING)
logging.getLogger('azure.identity').setLevel(logging.WARNING)

from src.utils.config_manager import Config
from sqlalchemy import create_engine, text
import pandas as pd

engine = create_engine(Config.get_pg_url())
print("Extraction des donnees...")

with engine.connect() as conn:
    df = pd.read_sql(text("""
        SELECT
            po_number, men_number, intermediaire, fournisseur,
            code_article, designation, quantite, prix_unitaire, total_prix,
            statut, date_statut, date_commande,
            etd_confirme, etd_reel, eta, date_livraison,
            n_bl, n_conteneur, retard_jours
        FROM achat.commande
        ORDER BY date_commande DESC NULLS LAST
    """), conn)

print(f"Lignes commande: {len(df)}")

def safe_str(v):
    if v is None or (isinstance(v, float) and v != v):  # NaN check
        return ''
    s = str(v)
    return '' if s in ('nan', 'NaT', 'None', 'NaN') else s

def safe_num(v):
    if v is None:
        return None
    try:
        f = float(v)
        return None if f != f else f  # NaN check
    except:
        return None

def fmt_date(v):
    if v is None:
        return ''
    s = safe_str(v)
    if not s:
        return ''
    m = re.match(r'(\d{4})-(\d{2})-(\d{2})', s)
    return f"{m.group(3)}/{m.group(2)}/{m.group(1)}" if m else s

# Nettoyer les valeurs NaN pandas explicitement
def row_val(row, col):
    v = row[col] if col in row.index else None
    if pd.isna(v) if not isinstance(v, str) else False:
        return None
    return v

# --- D.commandes ---
commandes = []
for _, r in df.iterrows():
    etd = None
    for col in ['etd_confirme', 'etd_reel']:
        val = r[col] if col in r.index else None
        if val is not None and not pd.isna(val):
            etd = val
            break
    commandes.append({
        "po":       safe_str(r['po_number']),
        "interm":   safe_str(r['intermediaire']),
        "frs":      safe_str(r['fournisseur']),
        "ref":      safe_str(r['code_article']),
        "desig":    safe_str(r['designation']),
        "qty":      safe_num(r['quantite']),
        "pu":       safe_num(r['prix_unitaire']),
        "total":    safe_num(r['total_prix']),
        "statut":   safe_str(r['statut']),
        "date_cmd": fmt_date(r['date_commande']),
        "etd":      fmt_date(etd),
        "eta":      fmt_date(r['eta'] if not pd.isna(r['eta']) else None),
        "bl":       safe_str(r['n_bl']),
        "ctn":      safe_str(r['n_conteneur']),
        "retard":   safe_num(r['retard_jours']),
    })

# --- D.statuts (par PO distinct) ---
po_statut = df.drop_duplicates('po_number')[['po_number','statut']]
statuts = [{"s": s, "n": int(n)} for s, n in po_statut['statut'].value_counts().items()]

# --- D.fournisseurs (top 10, dedup par PO) ---
caM = {}
for _, r in df.iterrows():
    po = safe_str(r['po_number'])
    frs = safe_str(r['fournisseur'])
    t = safe_num(r['total_prix']) or 0
    if po not in caM or caM[po]['ca'] < t:
        caM[po] = {'frs': frs, 'ca': t}

frs_agg = {}
for v in caM.values():
    f = v['frs']
    if not f:
        continue
    if f not in frs_agg:
        frs_agg[f] = {'ca': 0.0, 'n': 0}
    frs_agg[f]['ca'] += v['ca']
    frs_agg[f]['n'] += 1

fournisseurs = sorted(
    [{"f": f, "ca": round(v['ca'], 2), "n": v['n']} for f, v in frs_agg.items()],
    key=lambda x: x['ca'], reverse=True
)[:10]

# --- D.prix (flat array {c, d, dt, f, pu, q}) ---
prix_map = {}
for _, r in df.iterrows():
    ref = safe_str(r['code_article'])
    pu  = safe_num(r['prix_unitaire'])
    if not ref or pu is None:
        continue
    if ref not in prix_map:
        prix_map[ref] = safe_str(r['designation'])

prix = []
for _, r in df.iterrows():
    ref = safe_str(r['code_article'])
    pu  = safe_num(r['prix_unitaire'])
    if not ref or pu is None:
        continue
    prix.append({
        "c":  ref,
        "d":  prix_map.get(ref, ''),
        "dt": fmt_date(r['date_commande']),
        "f":  safe_str(r['fournisseur']),
        "pu": pu,
        "q":  safe_num(r['quantite']),
    })

# --- D.en_cours (champs courts : f, s, ret) ---
statuts_termines = {'Livrée', 'Annulée', 'Payée', 'Livree', 'Annulee', 'Payee'}
enc_pos = {}
for _, r in df.iterrows():
    statut = safe_str(r['statut'])
    if statut in statuts_termines:
        continue
    po = safe_str(r['po_number'])
    if not po or po in enc_pos:
        continue
    etd = None
    for col in ['etd_confirme', 'etd_reel']:
        val = r[col] if col in r.index else None
        if val is not None and not pd.isna(val):
            etd = val
            break
    enc_pos[po] = {
        "po":  po,
        "f":   safe_str(r['fournisseur']),
        "s":   statut,
        "etd": fmt_date(etd),
        "eta": fmt_date(r['eta'] if not pd.isna(r['eta']) else None),
        "ret": safe_num(r['retard_jours']),
        "ctn": safe_str(r['n_conteneur']),
    }
en_cours = list(enc_pos.values())

ca_total = sum(v['ca'] for v in caM.values())
print(f"\nKPIs:")
print(f"  Total POs     : {df['po_number'].nunique()}")
print(f"  En cours      : {len(en_cours)}")
print(f"  CA Import     : ${ca_total:,.0f}")
print(f"  Fournisseurs  : {len(frs_agg)}")
print(f"  Lignes prix   : {len(prix)}")

# Payload
payload = {
    "commandes":    commandes,
    "statuts":      statuts,
    "fournisseurs": fournisseurs,
    "prix":         prix,
    "en_cours":     en_cours,
    "last_update":  datetime.now().strftime("%d/%m/%Y %H:%M"),
}

# Serialiser sans caracteres dangereux
json_str = json.dumps(payload, ensure_ascii=True, separators=(',', ':'))
print(f"\nJSON: {len(json_str):,} chars, ensure_ascii=True")

# Lire le dashboard
html_path = r'C:\Users\abezille\dev\Data-Achat\dashboard_achats.html'
with open(html_path, 'r', encoding='utf-8') as f:
    html = f.read()

# Strategie 1 : remplacer le bloc JSON type="application/json" par <script>var D={...};</script>
new_data_block = f'<script>var D={json_str};</script>'

# Supprimer l'ancien bloc JSON (type application/json)
html_new = re.sub(
    r'<script type="application/json" id="D">.*?</script>',
    lambda m: new_data_block,   # lambda evite l'interpretation des \u comme regex
    html, flags=re.DOTALL
)

if html_new == html:
    # Pas trouve — inserer avant le main script
    html_new = html.replace('<script>\nvar D=JSON.parse', new_data_block + '\n<script>\nvar D=JSON.parse')
    print("Bloc non trouve — insertion avant main script")
else:
    print("Bloc JSON remplace par var D={...}")

# Strategie 2 : dans le main script, remplacer "var D=JSON.parse(...)" par "// D pre-loaded"
# Le D est deja defini dans le bloc data, pas besoin de le re-parser
html_new = re.sub(
    r'var D=JSON\.parse\(document\.getElementById\([\'"]D[\'"]\)\.textContent\);',
    '// D pre-loaded as JS variable',
    html_new
)
print("Remplacement var D=JSON.parse() : OK")

with open(html_path, 'w', encoding='utf-8') as f:
    f.write(html_new)

print(f"Dashboard genere : {html_path}")
print(f"Taille : {len(html_new):,} chars")
