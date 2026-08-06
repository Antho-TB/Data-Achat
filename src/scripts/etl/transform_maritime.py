# -*- coding: utf-8 -*-
"""
[ETL]
=============================================================================
TRANSFORM SUIVI MARITIME (source #4 Andréa) -> records achat.ot_transport
=============================================================================

Lit la feuille "SUIVI MARITIME TARRERIAS 2026" (gsheet en POC, xlsx serveur
TRANSITAIRE en prod -- décision 30/06) et produit des enregistrements compatibles
avec le loader `src.scripts.gmail.load_ot_gmail` (mêmes clés). Source-agnostique :
le coeur `transform_rows` prend des lignes brutes (list[list[str]]), l'adaptateur
de source (xlsx/csv) est en bout.

Voir docs/profil_suivi_maritime.md (mapping + 7 gotchas). Gérés ici :
- 2 colonnes ETA (estimée / confirmée) -> on prend la confirmée ;
- ETD estimé vs ATD réel -> etd_reel = ATD sinon ETD ;
- dates mois anglais SANS année -> inférence (oct-déc => campagne-1) ;
- calendrier hebdo en bas de feuille -> ignoré (stop au 1er marqueur SEM/jour) ;
- COMMANDE multi-PO -> éclatée et nettoyée (po_numbers) ;
- lignes sans conteneur (bookings futurs) -> exclues (PK ot_transport).

⚠️ Inférence d'année = heuristique (la feuille n'a pas d'année). À valider.

Usage :
    python -m src.scripts.etl.transform_maritime --file "2026 SUIVI MARITIME.xlsx" --out data/_maritime.json
    # puis : python -m src.scripts.gmail.load_ot_gmail --file data/_maritime.json --dry-run
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
from datetime import date, datetime, timezone
from typing import Optional

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(name)s -- %(message)s")
logger = logging.getLogger("transform_maritime")

# Positions de repli (0-based), correspondant a l'ancienne mise en page a 18
# colonnes. Elles ne servent QUE si la resolution par nom d'en-tete echoue.
COL_DEFAUT = {
    "fournisseur": 0, "commande": 1, "ref_qualitair": 2, "navire": 6,
    "etd": 7, "eta1": 8, "conteneur": 9, "atd": 10, "eta2": 11,
    "bl": 12, "date_confirmee": 15, "site": 17,
}

# Resolution des colonnes par NOM d'en-tete plutot que par position.
#
# Le fichier du transitaire est passe de 18 a 14 colonnes le 28/07/2026 : la
# colonne conteneur a glisse de l'index 9 a l'index 5, l'ATD de 10 a 8, l'ETA
# de 11 a 9, et la colonne BL a purement disparu. Avec des positions figees, le
# parser lisait "NAVIRE" la ou il croyait lire un numero de conteneur, ne
# trouvait aucun code ISO 6346 valide, et ecartait les 113 lignes une par une
# en silence. achat.ot_transport a cesse d'etre rafraichie sans qu'aucune
# erreur ne remonte.
#
# Junior Tip : sur un fichier tenu par un tiers, on ne se repere jamais a la
# position d'une colonne. On lit l'en-tete et on cherche les intitules. Le
# transitaire peut inserer une colonne quand il veut, ca ne casse plus rien.
#
# Chaque cle liste ses intitules acceptes, du plus precis au plus general.
ENTETES = {
    "fournisseur":    ("FRS", "FOURNISSEUR"),
    "commande":       ("REF COMMANDE", "COMMANDE", "PO"),
    "ref_qualitair":  ("REF QUALITAIR", "REF TRANSITAIRE", "DOSSIER"),
    "conteneur":      ("N° CONTENEUR", "N CONTENEUR", "CONTENEUR"),
    "navire":         ("NAVIRE", "VESSEL", "BATEAU"),
    "etd":            ("ETD",),
    "atd":            ("ATD",),
    "eta1":           ("ETA",),
    "eta2":           ("ETA CONFIRMEE", "ETA REELLE"),
    "bl":             ("N° BL", "N BL", "BL", "B/L", "CONNAISSEMENT"),
    "date_confirmee": ("DATE CONFIRMEE", "DDL CONFIRMEE", "LIVRAISON CONFIRMEE"),
    "heure":          ("HEURE", "HORAIRE", "H"),
    "ddl_estimee":    ("DDL ESTIMEE", "DATE ESTIMEE", "LIVRAISON ESTIMEE"),
    "site":           ("SITE", "DESTINATAIRE", "LIEU"),
}

# Separateurs possibles entre plusieurs BL dans une meme cellule.
RE_SEPARATEUR_BL = re.compile(r"[\s,;/]+")

# Un BL du transitaire : lettres puis chiffres, au moins 6 caracteres. Ecarte
# le bruit historique de la colonne ("DHL", "ATTACH", "ACKTRAY", "-", "/").
RE_BL = re.compile(r"^[A-Z0-9][A-Z0-9\-]{5,}$", re.IGNORECASE)


def extraire_bls(cellule: Optional[str]) -> list[str]:
    """
    Extrait tous les BL d'une cellule, un conteneur pouvant en porter plusieurs.

    Les BL sont edites par les FOURNISSEURS et un conteneur groupe plusieurs
    fournisseurs : la cellule contient donc regulierement plusieurs numeros,
    separes par un espace, une virgule ou un slash. Le code precedent prenait
    le premier et jetait les autres en silence.

    Args:
        cellule: contenu brut de la colonne BL.
    Returns:
        Liste de BL nettoyes, sans doublon, dans l'ordre d'apparition.
    """
    if not cellule:
        return []
    vus: list[str] = []
    for morceau in RE_SEPARATEUR_BL.split(str(cellule).strip()):
        candidat = morceau.strip().upper()
        if candidat and RE_BL.match(candidat) and any(c.isdigit() for c in candidat):
            if candidat not in vus:
                vus.append(candidat)
    return vus


def combiner_date_heure(date_iso: Optional[str], heure: Optional[str]) -> Optional[str]:
    """
    Assemble la date et l'heure de livraison confirmees en un horodatage.

    Le transitaire renseigne la date en colonne P et l'heure en colonne Q. Les
    deux comptent : Marlene organise le dechargement, un creneau du matin ou de
    l'apres-midi ne se prepare pas pareil. achat.ot_transport.date_livraison est
    un timestamp, l'heure y a donc sa place.

    Args:
        date_iso: date de livraison confirmee au format YYYY-MM-DD.
        heure: contenu de la colonne HEURE ("08:00", "8h", "14h30"...).
    Returns:
        Horodatage ISO, la date seule si l'heure est absente ou illisible.
    """
    if not date_iso:
        return None
    if not heure:
        return date_iso
    texte = str(heure).strip().lower().replace("h", ":")
    m = re.match(r"^(\d{1,2})(?::(\d{2}))?", texte)
    if not m:
        return date_iso
    h = int(m.group(1))
    mn = int(m.group(2) or 0)
    if not (0 <= h <= 23 and 0 <= mn <= 59):
        return date_iso
    return f"{date_iso}T{h:02d}:{mn:02d}:00"


def _normaliser(libelle: str) -> str:
    """Majuscules, espaces comprimes, degres et ponctuation neutralises."""
    texte = str(libelle).upper().replace("°", "").replace("N ", "N")
    return " ".join(texte.split())


def resoudre_colonnes(entete: list[str]) -> dict[str, Optional[int]]:
    """
    Associe chaque champ metier a son index de colonne, d'apres la ligne d'en-tete.

    Args:
        entete: ligne d'en-tete brute du fichier transitaire.
    Returns:
        Dictionnaire champ -> index, avec None quand la colonne est absente
        (cas du BL, disparu de la mise en page de juillet 2026).
    """
    normalises = [_normaliser(c) for c in entete]
    colonnes: dict[str, Optional[int]] = {}

    for champ, libelles in ENTETES.items():
        trouve: Optional[int] = None
        # Egalite stricte d'abord : evite que "ETA" attrape "DDL ESTIMEE".
        for libelle in libelles:
            cible = _normaliser(libelle)
            if cible in normalises:
                trouve = normalises.index(cible)
                break
        if trouve is None:
            for libelle in libelles:
                cible = _normaliser(libelle)
                for i, nom in enumerate(normalises):
                    if nom and cible in nom and i not in colonnes.values():
                        trouve = i
                        break
                if trouve is not None:
                    break
        colonnes[champ] = trouve

    # Cas des DEUX colonnes intitulees "ETA" : la mise en page historique du
    # transitaire porte une ETA previsionnelle puis une ETA confirmee, sans les
    # distinguer autrement que par leur position. Regle metier (profilage du
    # 30/06) : c'est la CONFIRMEE, donc la derniere, qui fait foi.
    indices_eta = [i for i, nom in enumerate(normalises)
                   if nom == "ETA" or nom.startswith("ETA ")]
    if len(indices_eta) >= 2:
        colonnes["eta1"] = indices_eta[0]
        colonnes["eta2"] = indices_eta[-1]

    manquants = [c for c in ("conteneur", "etd", "eta1") if colonnes.get(c) is None]
    if manquants:
        logger.warning("[ATTENTION] Colonnes essentielles absentes de l'en-tete (%s), "
                       "repli sur les positions historiques.", ", ".join(manquants))
        for champ in manquants:
            colonnes[champ] = COL_DEFAUT.get(champ)

    absentes = [c for c, i in colonnes.items() if i is None]
    if absentes:
        logger.info("[INFO] Colonnes non fournies par le transitaire, ignorees : %s",
                    ", ".join(absentes))

    # Le BL merite mieux qu'un log INFO (retour Marlene 29/07 : "les numeros de
    # BL ne remontent plus"). La copie serveur du suivi maritime n'a plus de
    # colonne BL depuis juillet 2026 : le chargement se deroule sans erreur et
    # remplit achat.ot_transport avec n_bl a NULL sur tous les conteneurs. Cote
    # metier, la colonne N° BL du tableau des paiements se vide, et Marlene
    # perd le croisement conteneur x BL dont elle se sert pour rapprocher une
    # liasse documentaire. Junior Tip : une source amputee d'une colonne n'est
    # pas une absence de donnee, c'est une source a changer -- ici le gsheet du
    # transitaire (SUIVI_MARITIME_PATH=gsheet), qui porte bien le BL.
    if colonnes.get("bl") is None:
        logger.warning("[ATTENTION] Aucune colonne BL dans cette source maritime : "
                       "achat.ot_transport sera chargee sans numero de BL et la "
                       "colonne N° BL se videra cote application. Basculer "
                       "SUIVI_MARITIME_PATH sur 'gsheet' (le fichier serveur est "
                       "une copie reduite a 14 colonnes, sans BL).")
    return colonnes
MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july",
     "august", "september", "october", "november", "december"], start=1)}
# ISO 6346 conteneur autonome.
# ISO 6346 : la 4e lettre est le code de categorie et vaut toujours U, J ou Z.
# Sans cette contrainte, les numeros de BL du transitaire (SZSE2604053...) ont
# exactement la meme forme qu'un conteneur et etaient ingeres comme tels.
RE_CONTAINER = re.compile(r"(?<![A-Za-z0-9])([A-Z]{3}[UJZ]\d{7})(?![A-Za-z0-9])")
RE_CAL_STOP = re.compile(r"\bSEM\b|^(janvier|février|mars|avril|mai|juin|juillet|"
                         r"ao[uû]t|septembre|octobre|novembre|décembre)\b", re.I)


RE_ISO_DATE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})(?:[ T]\d{2}:\d{2}:\d{2})?$")


def _date_livraison_effective(date_iso: Optional[str]) -> Optional[str]:
    """
    Ne retient une date de livraison que si elle est deja passee.

    Le fichier transitaire porte des dates de livraison planifiees, parfois a
    plusieurs semaines. Les enregistrer telles quelles reviendrait a declarer
    livre un conteneur encore en mer.

    Args:
        date_iso: date confirmee au format YYYY-MM-DD, ou None.
    Returns:
        La date si elle est passee ou du jour, None si elle est future.
    """
    if not date_iso:
        return None
    try:
        # La valeur peut porter une heure ("2026-09-08T08:00:00") depuis que la
        # colonne HEURE du transitaire est exploitee : on ne compare que le jour.
        if date.fromisoformat(str(date_iso)[:10]) > date.today():
            return None
    except ValueError:
        return None
    return date_iso


def _safe_maritime(y: int, mo: int, d: int) -> Optional[str]:
    try:
        return date(y, mo, d).isoformat()
    except ValueError:
        return None


def parse_maritime_date(raw: Optional[str], campaign_year: int = 2026) -> Optional[str]:
    """'2025-12-28 00:00:00' (ISO, cellule datetime Sheets) OU '28 December' / '6 March'
    (texte legacy sans année) -> ISO. Année inférée uniquement pour le format texte
    (oct-déc => campagne-1) ; le format ISO porte déjà sa propre année."""
    if not raw:
        return None
    s = str(raw).strip()
    m_iso = RE_ISO_DATE.match(s)
    if m_iso:
        y, mo, d = (int(x) for x in m_iso.groups())
        return _safe_maritime(y, mo, d)
    m = re.match(r"(\d{1,2})\s+([A-Za-z]+)", s)
    if not m:
        return None
    day = int(m.group(1))
    month = MONTHS.get(m.group(2).lower())
    if not month:
        return None
    year = campaign_year - 1 if month >= 10 else campaign_year
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return None


def clean_pos(commande: Optional[str]) -> list[str]:
    """Éclate COMMANDE multi-PO et nettoie (annotations (PP..), préfixes PO/GE#/TB#)."""
    if not commande:
        return []
    out: list[str] = []
    for tok in str(commande).replace("+", "/").split("/"):
        tok = re.sub(r"\(.*?\)", "", tok)                 # retire (PP 231)
        tok = re.sub(r"\b(PO|GE|TB)#?", "", tok, flags=re.I)  # préfixes
        tok = re.sub(r"[^0-9]", "", tok)                  # garde les chiffres
        if tok:
            out.append(tok.zfill(8) if len(tok) <= 8 else tok)
    return sorted(set(out))


def _cell(row: list[str], idx: int) -> Optional[str]:
    if idx < len(row):
        v = (row[idx] or "").strip()
        return v or None
    return None


def transform_rows(rows: list[list[str]], campaign_year: int = 2026,
                   source_fichier: str = "suivi_maritime",
                   date_transmission: Optional[str] = None) -> list[dict]:
    """Coeur source-agnostique : lignes brutes -> records ot_transport.

    Junior Tip : `date_transmission` est l'horodatage a comparer chronologiquement
    (spec ETA §4/§7.2) -- decision 23/07 : c'est la date du FICHIER (mtime), pas la
    date d'ingestion ETL, car le fichier maritime est un snapshot sans date par ligne.
    Propage sur chaque record pour que load_ot_gmail applique la preseance
    chronologique et decide si un changement doit etre historise.
    """
    # 1) localiser l'en-tête réel
    #
    # Le transitaire a renomme la 1re colonne "FOURNISSEUR" en "FRS" (constate
    # le 28/07/2026 sur le fichier serveur). Le parser ne trouvait plus
    # l'en-tete, renvoyait 0 record sans erreur, et achat.ot_transport cessait
    # silencieusement d'etre rafraichie : plus aucune mise a jour d'ETA, de BL
    # ni de navire, alors que les logs affichaient "113 lignes" en amont.
    #
    # Junior Tip : on valide desormais l'en-tete sur PLUSIEURS colonnes plutot
    # que sur un seul libelle. Un fichier tenu par un tiers voit ses intitules
    # changer sans preavis ; s'accrocher a un seul mot rend l'ETL muet au lieu
    # de bruyant. Et si rien ne matche, on leve au lieu de renvoyer une liste
    # vide, pour que l'echec se voie.
    entetes_attendus = ("FRS", "FOURNISSEUR")
    marqueurs_ligne = ("CONTENEUR", "NAVIRE", "ETD", "ETA")

    def _est_entete(ligne: list[str]) -> bool:
        if not ligne:
            return False
        premiere = str(ligne[0]).strip().upper()
        if not any(premiere.startswith(e) for e in entetes_attendus):
            return False
        contenu = " ".join(str(c).upper() for c in ligne)
        return sum(m in contenu for m in marqueurs_ligne) >= 2

    start = next((i for i, r in enumerate(rows) if _est_entete(r)), None)
    if start is None:
        raise ValueError(
            "En-tete du SUIVI MARITIME introuvable. Attendu une ligne commencant par "
            f"{entetes_attendus} et contenant au moins 2 de {marqueurs_ligne}. "
            "Le transitaire a probablement renomme ses colonnes : verifier le fichier "
            "et mettre a jour entetes_attendus / la table COL de ce module."
        )

    # 2) resoudre les colonnes d'apres l'en-tete reel, jamais par position figee
    COL = resoudre_colonnes(rows[start])

    def _col(row: list[str], champ: str) -> Optional[str]:
        """Lit une cellule par nom de champ ; None si la colonne n'existe pas."""
        index = COL.get(champ)
        return _cell(row, index) if index is not None else None

    records: list[dict] = []
    skipped_no_cont = 0
    for row in rows[start + 1:]:
        col0 = _cell(row, 0) or ""
        # 3) stop au calendrier hebdo
        if RE_CAL_STOP.search(col0):
            break
        conteneurs = RE_CONTAINER.findall((_col(row, "conteneur") or "").upper())
        if not conteneurs:
            skipped_no_cont += 1   # booking futur sans conteneur -> hors ot_transport
            continue
        bls = extraire_bls(_col(row, "bl"))
        rec_base = {
            # n_bl garde le BL principal pour l'affichage existant et les vues.
            # La liste complete part dans bls, chargee dans achat.ot_transport_bl.
            "n_bl": bls[0] if bls else None,
            "bls": bls,
            "etd_reel": parse_maritime_date(_col(row, "atd"), campaign_year)
                        or parse_maritime_date(_col(row, "etd"), campaign_year),
            "eta": parse_maritime_date(_col(row, "eta2"), campaign_year)
                   or parse_maritime_date(_col(row, "eta1"), campaign_year),
            # date_livraison = livraison REELLEMENT effectuee sur site. Toute
            # l'application lit ce champ comme un booleen "livre" : l'onglet
            # Conteneurs en deduit le nombre et la valeur des conteneurs en
            # transit, v_previsionnel s'en sert pour est_parti et est_en_retard.
            #
            # On ne retient donc QUE la date confirmee, jamais la date estimee,
            # et seulement si elle est deja passee. Alimenter ce champ avec une
            # date previsionnelle future faisait passer pour livres tous les
            # conteneurs encore en mer : "Valeur en transit" tombait a 0 alors
            # que 4 conteneurs valant 270 000 $US naviguaient.
            "date_livraison": _date_livraison_effective(
                combiner_date_heure(
                    parse_maritime_date(_col(row, "date_confirmee"), campaign_year),
                    _col(row, "heure"))),
            "transport": _col(row, "navire"),
            "transitaire": "QUALITAIR",
            "n_facture": None,
            "lieu_livraison": _col(row, "site"),
            "po_numbers": clean_pos(_col(row, "commande")) or None,
            "source_fichier": source_fichier,
            "date_transmission": date_transmission,
        }
        # Garde-fou rollover : un depart (ETD reel) ne peut pas etre posterieur
        # a l'arrivee (ETA). Cas des cellules datetime ISO portant une annee
        # absolue erronee (ex. "25 December" saisi 2026 au lieu de 2025, non
        # couvert par la regle month>=10 qui ne vaut que pour le format texte).
        etd, eta = rec_base["etd_reel"], rec_base["eta"]
        if etd and eta and etd > eta:
            try:
                d0 = date.fromisoformat(etd)
                corrected = d0.replace(year=d0.year - 1).isoformat()
                logger.warning(
                    "[ATTENTION] ETD %s > ETA %s (conteneur %s) : rollover annee applique -> ETD %s.",
                    etd, eta, conteneurs[0], corrected)
                rec_base["etd_reel"] = corrected
            except ValueError:
                logger.warning("[ATTENTION] ETD %s > ETA %s (conteneur %s) : correction impossible, laisse tel quel.",
                               etd, eta, conteneurs[0])
        for cont in conteneurs:   # 1 record par conteneur (PK)
            records.append({"n_conteneur": cont, **rec_base})

    logger.info("[SUCCÈS] SUIVI MARITIME : %d conteneur(s) transformé(s) (%d ligne(s) sans conteneur ignorée(s)).",
                len(records), skipped_no_cont)
    return records


# Classeur "SUIVI MARITIME TARRERIAS 2026", tenu avec le transitaire.
# Source de verite depuis le 28/07 : c'est la que le travail se fait, le fichier
# serveur n'en etant qu'une copie reduite (14 colonnes, sans BL).
GSHEET_MARITIME_ID = "1hP73oivXrB8o8I7pkrGh7y6nPzn0ccfW"


# Seul onglet portant le suivi conteneurs. Les autres (AVRIL a DECEMBRE) sont des
# plannings de livraison par semaine, sans colonne BL : les lire n'apporterait
# rien et melangerait leurs lignes a celles du suivi. Constate le 06/08/2026.
ONGLETS_UTILES: frozenset[str] = frozenset({"SUIVI"})


def _read_rows_gsheet(spreadsheet_id: str) -> list[list[str]]:
    """
    Lit le suivi maritime directement dans le classeur partage du transitaire.

    Le classeur n'est PAS un Google Sheet natif : c'est un .xlsx depose dans
    Drive par QUALITAIR (proprietaire lbonnet@qualitairsea.com). L'API Sheets le
    refusait, ce qui faisait echouer cette fonction depuis sa mise en place : le
    repli d'extract.py retombait alors sur la copie serveur a 14 colonnes, sans
    colonne BL. C'est la cause du bug des numeros de BL manquants. lire_classeur()
    choisit l'API a utiliser d'apres le type MIME reel.

    Args:
        spreadsheet_id: identifiant du classeur Drive.
    Returns:
        Lignes brutes, meme format positionnel que _read_rows.
    """
    from src.utils.gsheets import lire_classeur

    onglets = lire_classeur(spreadsheet_id)
    retenus = [(nom, grille) for nom, grille in onglets
               if nom.strip().upper() in ONGLETS_UTILES]

    if not retenus:
        # Repli plutot qu'echec : le transitaire peut renommer son onglet. On le
        # dit fort, parce que lire tous les onglets melange les plannings mensuels
        # au suivi conteneurs et gonfle le compteur de lignes ignorees.
        logger.warning("[ATTENTION] Aucun onglet %s dans le classeur (presents : %s). "
                       "Repli sur la lecture de tous les onglets.",
                       "/".join(sorted(ONGLETS_UTILES)),
                       ", ".join(nom for nom, _ in onglets) or "aucun")
        retenus = onglets
    else:
        ignores = [nom for nom, _ in onglets
                   if nom.strip().upper() not in ONGLETS_UTILES]
        if ignores:
            logger.info("[INFO] Onglets ignores (plannings sans BL) : %s.",
                        ", ".join(ignores))

    lignes: list[list[str]] = []
    for nom_onglet, grille in retenus:
        logger.info("[INFO] Onglet retenu '%s' : %d ligne(s).", nom_onglet, len(grille))
        for ligne in grille:
            lignes.append([str(c) if c is not None else "" for c in ligne])
    return lignes


def _read_rows(path: str) -> list[list[str]]:
    """Adaptateur source : xlsx/csv -> lignes brutes (header=None, positionnel)."""
    import pandas as pd
    if path.lower().endswith((".xlsx", ".xls", ".xlsm")):
        df = pd.read_excel(path, header=None, dtype=str)
    else:
        df = pd.read_csv(path, header=None, dtype=str)
    return df.fillna("").astype(str).values.tolist()


def main() -> int:
    ap = argparse.ArgumentParser(description="Transform SUIVI MARITIME -> JSON ot_transport.")
    ap.add_argument("--file", required=True, help="xlsx/csv (gsheet exporté en POC, serveur TRANSITAIRE en prod).")
    ap.add_argument("--out", default="", help="JSON de sortie (sinon stdout).")
    ap.add_argument("--campaign-year", type=int, default=2026)
    args = ap.parse_args()

    rows = _read_rows(args.file)
    # Date du fichier (mtime), pas la date d'ingestion -- decision metier 23/07 (spec ETA §7.2).
    # Suppose que le mtime survit a la copie SMB/Drive depuis la source transitaire ;
    # a revalider si le fichier est retelecharge d'une maniere qui reinitialise le mtime.
    try:
        mtime = os.path.getmtime(args.file)
        date_transmission = datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()
    except OSError:
        date_transmission = None
        logger.warning("[ATTENTION] mtime du fichier illisible -- date_transmission absente (pas de preseance chronologique pour ce lot).")
    records = transform_rows(rows, args.campaign_year, source_fichier=args.file.split("/")[-1],
                             date_transmission=date_transmission)
    payload = json.dumps(records, ensure_ascii=False, indent=2)
    if args.out:
        from pathlib import Path
        Path(args.out).write_text(payload, encoding="utf-8")
        logger.info("[SUCCÈS] %d record(s) -> %s", len(records), args.out)
    else:
        # print assume ici : sortie de donnees du CLI, pas un log (cf. parse_bl).
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
