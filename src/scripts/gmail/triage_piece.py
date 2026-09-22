# -*- coding: utf-8 -*-
"""
[ETL]
=============================================================================
TRI PREALABLE DES PIECES JOINTES, AVANT APPEL AU MODELE MULTIMODAL
=============================================================================

POURQUOI CE MODULE
Mesure du 06/08/2026 sur data/PJ/202607, poste de Marlene : sur les 11 premieres
pieces jointes analysees, 11 sur 11 n'etaient PAS des pieces comptables (BL,
packing lists, avis de retard, confirmations d'embarquement QUALITAIR). Chacune a
coute un appel Gemini multimodal complet, environ 5 secondes, pour conclure qu'un
fichier nomme "...-PACKING LIST.PDF" n'est pas une facture.

Le modele multimodal reste indispensable pour EXTRAIRE un montant : les pieces
arrivent en PDF propre, en scan ou en photo JPEG, et des expressions regulieres
y seraient silencieusement fausses. Ce module ne remet pas cela en cause. Il
retire au modele la seule tache qu'il fait cher et mal : le TRI.

PRINCIPE : ON NE REJETTE JAMAIS SUR UNE INTUITION
Un document n'est ecarte que si une preuve peu couteuse le dit. Dans le doute, on
paie l'appel. Les deux erreurs possibles n'ont pas le meme prix : envoyer un BL au
modele coute un appel flash, alors qu'ecarter a tort une facture prive Marlene
d'un montant et la fait payer sur le chiffre du fichier IMPORT. C'est exactement
le defaut du 29/07 que ce chantier corrige. Le biais est donc volontairement
asymetrique.

TROIS ETAGES, DU MOINS CHER AU PLUS CHER
1. Nom de fichier      : cout nul. Ecarte les gabarits transitaire connus.
2. Couche texte native : cout ~20 ms par page (pdfplumber). Ecarte un PDF texte
                         qui ne porte aucun marqueur comptable.
3. Modele multimodal   : ~5 s et un appel. Tout le reste, dont les scans et les
                         JPEG, qui n'ont pas de couche texte exploitable.

LE CAS DE LA LIASSE, ET POURQUOI L'ETAGE 1 NE DECIDE PAS SEUL SUR UN PDF
Les fournisseurs envoient des LIASSES : un seul PDF qui enchaine connaissement,
packing list, puis facture. Marlene en a cite une le 29/07 (JIT GLOBAL). Une telle
liasse porte souvent un nom d'expedition, du type "BL-SZSE2606480.pdf". Ecarter
sur le nom seul y perdrait la facture, sans trace et sans erreur.

Un rejet fonde sur le nom d'un PDF est donc TOUJOURS soumis a la couche texte :
si un marqueur comptable apparait n'importe ou dans le document, le rejet est
annule et la piece part au modele. Lire tout le texte coute quelques dizaines de
millisecondes, contre 5 secondes pour l'appel qu'on cherche a eviter : la
verification est moins chere que l'erreur qu'elle previent.

Usage :
    from src.scripts.gmail.triage_piece import trier

    v = trier(chemin)
    if v.decision == "non_comptable":
        continue            # zero appel modele
    # sinon -> parse_facture(chemin)

Mesure du gain, sans declencher un seul appel :
    python -m src.scripts.gmail.triage_piece --folder data/PJ
"""
from __future__ import annotations

import argparse
import json
import logging
import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Literal

logger = logging.getLogger(__name__)

Decision = Literal["non_comptable", "a_analyser"]

# Extensions traitables. Aligne sur parse_facture.EXTENSIONS_SUPPORTEES.
EXTENSIONS_SUPPORTEES: set[str] = {".pdf", ".jpg", ".jpeg", ".png", ".webp"}

# ---------------------------------------------------------------------------
# Etage 1 : gabarits de nom de fichier
# ---------------------------------------------------------------------------
# Libelles releves sur les gabarits automatiques du transitaire QUALITAIR SEA
# DIMOTRANS et de TB China (mesure du 06/08/2026). Ils sont stables parce qu'ils
# sont generes par un logiciel, pas tapes a la main : c'est ce qui rend la regle
# fiable.
#
# REGLE D'OR pour ajouter une entree ici : le libelle doit designer un TYPE DE
# DOCUMENT qui n'est jamais comptable. Ne jamais mettre un nom de fournisseur, un
# numero de PO ni un mois : un fournisseur qui envoie des BL envoie aussi des
# factures.
MOTIFS_NON_COMPTABLES: tuple[str, ...] = (
    r"packing\s*list",
    r"\bbl[-_\s]",                       # BL-SZSE2606480-...
    r"connaissement",
    r"bill\s+of\s+lading",
    r"avis\s+de\s+retard",
    r"confirmation\s+d[e']\s*embarquement",
    r"pr[ée]vision\s+d[e']\s*embarquement",
    r"confirmation\s+de\s+r[ée]servation",
    r"confirmation\s+de\s+date\s+de\s+livraison",
    r"notification\s+commande",
    r"liste\s+tarifaire",
    r"\btransit\b",
    r"certificat\s+d[e']\s*analyse",
    r"rapport\s+d[e']\s*inspection",
)
_RE_NON_COMPTABLE = re.compile("|".join(MOTIFS_NON_COMPTABLES), re.IGNORECASE)

# Un nom de fichier qui annonce une piece comptable l'emporte sur la liste
# ci-dessus : le transitaire envoie parfois "Facture - Confirmation
# d'embarquement ...".
MOTIFS_COMPTABLES: tuple[str, ...] = (
    r"\bfacture\b", r"\binvoice\b", r"\bproforma\b", r"\bpro\s*forma\b",
    r"credit\s*note", r"note\s+de\s+cr[ée]dit", r"\bdebit\s*note\b",
    r"\bavoir\b", r"\bdeposit\b", r"\bacompte\b",
)
_RE_COMPTABLE = re.compile("|".join(MOTIFS_COMPTABLES), re.IGNORECASE)

# ---------------------------------------------------------------------------
# Etage 2 : marqueurs dans la couche texte
# ---------------------------------------------------------------------------
# Presents sur toute piece comptable, quelle que soit la langue du fournisseur.
MARQUEURS_TEXTE: tuple[str, ...] = (
    r"\binvoice\b", r"\bfacture\b", r"\bproforma\b", r"credit\s*note",
    r"total\s+amount", r"montant\s+total", r"amount\s+due", r"net\s+to\s+pay",
    r"net\s+a\s+payer", r"total\s+ttc", r"total\s+ht", r"grand\s+total",
    r"\bsubtotal\b", r"\bbank\s+details?\b", r"\biban\b", r"\bswift\b",
    r"payment\s+terms", r"\bbeneficiary\b",
)
_RE_MARQUEURS = re.compile("|".join(MARQUEURS_TEXTE), re.IGNORECASE)

# En dessous de ce volume, on considere qu'il n'y a pas de couche texte
# exploitable : c'est un scan ou une photo. On ne conclut donc rien et on laisse
# le modele multimodal decider.
SEUIL_TEXTE_EXPLOITABLE: int = 200  # caracteres

# Plafond de pages lues. Une liasse fait rarement plus de quelques pages, mais un
# catalogue fournisseur peut en faire cent : au-dela de ce plafond on arrete et on
# le journalise, pour ne jamais tronquer en silence.
PAGES_MAX: int = 15


@dataclass(frozen=True)
class Verdict:
    """
    Resultat du tri.

    Attributes:
        decision: "non_comptable" (ecarte sans appel modele) ou "a_analyser".
        etage: quel etage a tranche ("nom", "texte", "liasse", "defaut").
        motif: la preuve, en clair, pour que le journal soit auditable. Un tri
            qui ecarte un document sans dire pourquoi est impossible a corriger
            six mois plus tard.
    """
    decision: Decision
    etage: str
    motif: str


def _texte_pdf(chemin: Path) -> str:
    """
    Couche texte native d'un PDF, ou "" s'il n'y en a pas.

    Ne fait JAMAIS d'OCR : l'etage doit rester quasi gratuit, alors que l'OCR de
    parse_bl.py rasterise a 300 dpi, ce qui coute plus cher que l'appel qu'on
    cherche a eviter.

    Junior Tip : cette fonction ne leve jamais. Un PDF corrompu ou protege par
    mot de passe ne doit pas faire tomber le tri, il doit renvoyer une chaine
    vide, ce qui conduit a payer l'appel. Le tri est une optimisation de cout,
    jamais un point de panne du pipeline.
    """
    if chemin.suffix.lower() != ".pdf":
        return ""
    try:
        import pdfplumber  # dependance locale, deja requise par parse_bl.py
    except ImportError:
        logger.warning("[ATTENTION] pdfplumber absent : l'etage texte est saute, "
                       "les rejets sur nom de fichier ne sont plus verifies.")
        return ""
    try:
        morceaux: list[str] = []
        with pdfplumber.open(chemin) as pdf:
            total = len(pdf.pages)
            for page in pdf.pages[:PAGES_MAX]:
                morceaux.append(page.extract_text() or "")
            if total > PAGES_MAX:
                logger.info("[INFO] %s : %d pages, seules les %d premieres sont "
                            "lues pour le tri.", chemin.name, total, PAGES_MAX)
        return "\n".join(morceaux)
    except Exception as exc:
        # Un PDF illisible n'est pas un PDF non comptable : on laisse la suite
        # decider plutot que d'ecarter sur une panne de librairie.
        logger.debug("%s : lecture texte impossible (%s).", chemin.name, exc)
        return ""


def trier(chemin: Path) -> Verdict:
    """
    Decide si une piece jointe merite un appel au modele multimodal.

    Args:
        chemin: fichier a trier.
    Returns:
        Verdict. Seul "non_comptable" autorise a sauter l'appel modele.
    """
    nom = chemin.name

    if chemin.suffix.lower() not in EXTENSIONS_SUPPORTEES:
        return Verdict("non_comptable", "nom",
                       f"extension {chemin.suffix or 'absente'} non traitable")

    # Etage 1 : le nom annonce une piece comptable. Aucune verification a faire,
    # on paie.
    if _RE_COMPTABLE.search(nom):
        return Verdict("a_analyser", "nom", "le nom annonce une piece comptable")

    rejet_nom = _RE_NON_COMPTABLE.search(nom)

    # Etage 2 : couche texte. Lue AUSSI quand l'etage 1 veut rejeter, pour ne pas
    # perdre une liasse dont le nom parle d'expedition mais qui contient une
    # facture plus loin (cf. en-tete du module).
    texte = _texte_pdf(chemin)
    texte_exploitable = len(texte.strip()) >= SEUIL_TEXTE_EXPLOITABLE
    marqueur = _RE_MARQUEURS.search(texte) if texte_exploitable else None

    if rejet_nom:
        if marqueur:
            return Verdict(
                "a_analyser", "liasse",
                f"nom d'expedition ('{rejet_nom.group(0)}') mais marqueur "
                f"comptable dans le texte ('{marqueur.group(0)}')")
        if texte_exploitable:
            return Verdict("non_comptable", "nom",
                           f"gabarit transitaire ('{rejet_nom.group(0)}'), "
                           "confirme par la couche texte")
        # Pas de couche texte : le nom est la seule information disponible. Les
        # gabarits sont generes par logiciel, donc precis, mais ce rejet reste le
        # seul du module qui ne soit pas verifie. Journalise pour rester auditable.
        return Verdict("non_comptable", "nom",
                       f"gabarit transitaire ('{rejet_nom.group(0)}'), "
                       "non verifiable faute de couche texte")

    if texte_exploitable:
        if marqueur:
            return Verdict("a_analyser", "texte",
                           f"marqueur comptable dans le texte ('{marqueur.group(0)}')")
        return Verdict("non_comptable", "texte",
                       "couche texte lisible, aucun marqueur comptable")

    # Etage 3 : scan, photo JPEG ou PDF sans couche texte. On ne sait pas trancher
    # a bas cout, donc on paie. C'est le cas que le modele multimodal justifie a
    # lui seul.
    return Verdict("a_analyser", "defaut",
                   "pas de couche texte exploitable (scan ou image)")


def trier_dossier(dossier: Path) -> tuple[list[Path], list[tuple[Path, Verdict]]]:
    """
    Trie un dossier entier.

    Returns:
        (a_analyser, ecartes). ecartes porte le Verdict, pour le journal.
    """
    a_analyser: list[Path] = []
    ecartes: list[tuple[Path, Verdict]] = []
    fichiers = [p for p in sorted(dossier.rglob("*"))
                if p.is_file() and p.suffix.lower() in EXTENSIONS_SUPPORTEES]
    for fichier in fichiers:
        verdict = trier(fichier)
        if verdict.decision == "non_comptable":
            ecartes.append((fichier, verdict))
        else:
            a_analyser.append(fichier)
    total = len(fichiers)
    logger.info("[TRI] %d piece(s) : %d a analyser, %d ecartee(s) sans appel "
                "modele%s.", total, len(a_analyser), len(ecartes),
                f" ({100.0 * len(ecartes) / total:.0f} %)" if total else "")
    return a_analyser, ecartes


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s -- %(message)s")
    ap = argparse.ArgumentParser(
        description="Tri prealable des pieces jointes, sans aucun appel au modele.")
    ap.add_argument("--file", type=str, help="Une piece jointe.")
    ap.add_argument("--folder", type=str, help="Dossier de PJ (recursif).")
    ap.add_argument("--out", type=str, default="", help="Fichier JSON de sortie.")
    args = ap.parse_args()

    if args.file:
        chemin = Path(args.file)
        lignes = [{"fichier": chemin.name, **asdict(trier(chemin))}]
    elif args.folder:
        dossier = Path(args.folder)
        a_analyser, ecartes = trier_dossier(dossier)
        lignes = [{"fichier": str(p.relative_to(dossier)),
                   "decision": "a_analyser", "etage": "", "motif": ""}
                  for p in a_analyser]
        lignes += [{"fichier": str(p.relative_to(dossier)), **asdict(v)}
                   for p, v in ecartes]
    else:
        ap.error("Fournir --file ou --folder.")
        return 2

    charge = json.dumps(lignes, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(charge, encoding="utf-8")
        logger.info("[SUCCES] %d ligne(s) -> %s", len(lignes), args.out)
    else:
        # print assume : sortie de DONNEES du CLI, redirigeable (| jq, > fichier).
        print(charge)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
