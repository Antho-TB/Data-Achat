# -*- coding: utf-8 -*-
"""
[ETL]
=============================================================================
PARSEUR DE PIECE COMPTABLE (PDF / IMAGE) -> JSON pour achat.facture_fournisseur
=============================================================================

Lit une piece jointe de mail fournisseur (facture, note de credit, deposit) et
en extrait le MONTANT, sa DEVISE et ses rattachements, par appel a un modele
multimodal Gemini.

POURQUOI CE MODULE EXISTE
Le 29/07/2026, Marlene a regle des fournisseurs en s'appuyant sur l'onglet
Previsionnel, et constate que le montant affiche n'etait pas celui de la
facture recue par mail (HONGXING : 6 403,20 EUR sur la liasse). Diagnostic :
FUSEAU ne connaissait AUCUN montant de facture. Les pieces jointes etaient bien
toutes telechargees par fetch_attachments.py, mais le seul parseur en place,
parse_bl.py, a un perimetre EXPEDITION (conteneur, BL, ETD, ETA, transitaire) :
il lit le NUMERO de facture, jamais son MONTANT, parce que sa table cible
achat.ot_transport n'a aucune colonne monetaire. Les montants affiches
venaient donc a 100 % de achat.commande, alimentee par IMPORT 2026.xlsx, que le
metier doit justement cesser d'utiliser.

POURQUOI UN MODELE ET PAS DES EXPRESSIONS REGULIERES
Les factures arrivent en PDF propre, en PDF scanne et en photo JPEG, avec un
gabarit different par fournisseur. Une regex de montant y serait fragile, et
surtout silencieusement fausse : elle ramenerait un sous-total, une remise ou
un prix unitaire en croyant tenir le total a payer. Sur une donnee qui declenche
un virement, un faux positif coute plus cher qu'une absence de valeur. Le modele
rend donc AUSSI un niveau de confiance et le libelle exact qu'il a lu, pour que
l'humain puisse verifier sans rouvrir le PDF.

CE QUE CE MODULE NE FAIT PAS
Aucune ecriture en base (l'insertion est faite par load_facture.py), aucune
conversion de devise, aucun arbitrage entre le montant de la piece et celui du
fichier IMPORT. Il rapporte ce que le document dit. L'ecart est un sujet
d'affichage et de decision metier, pas d'extraction.

Usage :
    python -m src.scripts.gmail.parse_facture --file data/PJ/202607/facture.pdf
    python -m src.scripts.gmail.parse_facture --folder data/PJ --out data/PJ/_factures.json
"""
from __future__ import annotations

import argparse
import json
import logging
import mimetypes
import time
from pathlib import Path
from typing import Any, Optional

from src.utils.config_manager import Config

logger = logging.getLogger(__name__)

# Extensions traitables par le modele multimodal. Les classeurs Excel sont
# volontairement exclus : une facture en .xlsx se lit avec pandas, sans appel
# payant, et ce cas n'a pas encore ete observe cote fournisseurs.
EXTENSIONS_SUPPORTEES: set[str] = {".pdf", ".jpg", ".jpeg", ".png", ".webp"}

TYPES_PIECE: tuple[str, ...] = (
    "facture", "note_credit", "deposit", "avance", "proforma")

# Schema de sortie impose au modele. Une reponse en texte libre obligerait a
# reparser du francais approximatif : on demande directement la structure de la
# table cible, champ pour champ.
SCHEMA_REPONSE: dict[str, Any] = {
    "type": "object",
    "properties": {
        "est_piece_comptable": {"type": "boolean"},
        "type_piece": {"type": "string", "enum": list(TYPES_PIECE)},
        "n_facture": {"type": "string", "nullable": True},
        "fournisseur": {"type": "string", "nullable": True},
        "date_piece": {"type": "string", "nullable": True},
        "montant": {"type": "number", "nullable": True},
        "montant_ht": {"type": "number", "nullable": True},
        "devise": {"type": "string", "nullable": True},
        "po_numbers": {"type": "array", "items": {"type": "string"}},
        "n_conteneur": {"type": "string", "nullable": True},
        "n_bl": {"type": "string", "nullable": True},
        "libelle_montant_lu": {"type": "string", "nullable": True},
        "confiance": {"type": "number"},
        "commentaire": {"type": "string", "nullable": True},
    },
    "required": ["est_piece_comptable", "type_piece", "confiance"],
}

# Consigne metier. Ecrite en francais : c'est la langue dans laquelle Marlene
# et Andrea decrivent leurs regles, et le prompt doit rester relisable par elles.
CONSIGNE = """Tu analyses une piece jointe recue par le service Achats de TB Groupe,
un fabricant francais de coutellerie qui importe depuis la Chine.

Determine d'abord s'il s'agit d'une piece COMPTABLE (facture, note de credit,
deposit, avance, facture proforma). Un connaissement (BL), une packing list, un
certificat d'inspection ou un echange de mails ne sont PAS des pieces
comptables : dans ce cas renvoie est_piece_comptable = false et arrete la.

Si c'est une piece comptable, extrais :
- montant : le TOTAL REELLEMENT DU au fournisseur pour cette piece. Jamais un
  sous-total, jamais un prix unitaire, jamais un montant de ligne. Si le
  document distingue un total TTC et un total HT, montant = le total a payer.
- Pour une NOTE DE CREDIT (credit note), renvoie le montant en NEGATIF.
- devise : le code exact ecrit sur la piece (EUR, USD, CNY). Ne convertis
  jamais, ne devine jamais : si la devise n'est pas ecrite, renvoie null.
- n_facture : la reference de la piece telle qu'imprimee.
- po_numbers : tous les numeros de commande TB visibles, sur 8 chiffres avec
  les zeros de tete (exemple 00017281).
- n_conteneur : uniquement une reference ISO 6346 (4 lettres dont la 4e vaut U,
  J ou Z, puis 7 chiffres). Ne confonds pas avec un numero de BL, qui a la
  meme allure (exemple SZSE2604053 est un BL, pas un conteneur).
- libelle_montant_lu : recopie mot pour mot le libelle de la ligne d'ou tu as
  tire le montant (exemple "TOTAL AMOUNT USD"). Cela permet une verification
  humaine sans rouvrir le document.
- confiance : entre 0 et 1. Sois severe. Un scan illisible, un total ambigu,
  plusieurs totaux concurrents, une devise absente : descends sous 0.5 et
  explique en commentaire.

Ne devine aucune valeur absente : renvoie null. Une valeur manquante est
recuperable par une saisie humaine, une valeur inventee provoque un virement du
mauvais montant."""


def _client_gemini():
    """
    Instancie le client Gemini, ou leve si aucune cle n'est disponible.

    Junior Tip : on leve au lieu de renvoyer None. Une source d'extraction
    indisponible n'est pas une facture sans montant : confondre les deux
    ferait passer une panne d'authentification pour un document vide, et
    remplirait la base de zeros credibles.

    Raises:
        RuntimeError: SDK absent, ou aucune cle Gemini configuree.
    """
    try:
        from google import genai
    except ImportError as exc:
        raise RuntimeError(
            "SDK google-genai absent : pip install google-genai") from exc

    cle = Config.get_gemini_api_key()
    if not cle:
        raise RuntimeError(
            "Aucune cle Gemini disponible (ni GEMINI_API_KEY dans config/.env, "
            "ni secret GEMINI-API-KEY dans le Key Vault).")
    return genai.Client(api_key=cle)


def _mime_type(chemin: Path) -> str:
    """Type MIME de la piece jointe, deduit de l'extension."""
    devine, _ = mimetypes.guess_type(chemin.name)
    return devine or "application/pdf"


def _appel_modele(client: Any, chemin: Path, modele: str) -> dict[str, Any]:
    """
    Envoie la piece au modele et renvoie sa reponse structuree.

    Borne dans le temps et reprend sur erreur de TRANSPORT. Sans timeout, un
    appel qui ne rend jamais la main fige le lot entier : constate le 06/08/2026
    sur le poste de Marlene, plus de 4 minutes sur un PDF de 0,4 Mo.

    Junior Tip : on ne reprend QUE les pannes de transport (timeout, 429, 503).
    Une reponse vide ou non JSON n'est pas reprise, parce que la temperature est
    nulle : le meme document redonnerait exactement la meme mauvaise reponse, et
    la reprise ne ferait que payer trois fois la meme erreur. Distinguer les deux
    familles est ce qui separe une reprise utile d'une boucle couteuse.

    Args:
        client: client google-genai deja instancie.
        chemin: fichier a lire (PDF ou image).
        modele: nom exact du modele, epingle par la Config.
    Returns:
        Dictionnaire conforme a SCHEMA_REPONSE.
    Raises:
        ValueError: si la reponse du modele n'est pas un JSON exploitable.
        TimeoutError: si toutes les tentatives de transport ont echoue.
    """
    from google.genai import types

    est_escalade = modele == Config.MODELE_FACTURE_ESCALADE
    timeout_ms = (Config.GEMINI_TIMEOUT_ESCALADE_MS if est_escalade
                  else Config.GEMINI_TIMEOUT_MS)

    piece = types.Part.from_bytes(
        data=chemin.read_bytes(), mime_type=_mime_type(chemin))
    config = types.GenerateContentConfig(
        # Temperature nulle : sur une extraction comptable, on veut le meme
        # resultat au deuxieme passage, pas une variante plausible.
        temperature=0.0,
        response_mime_type="application/json",
        response_schema=SCHEMA_REPONSE,
        http_options=types.HttpOptions(timeout=timeout_ms),
    )

    derniere: Optional[Exception] = None
    for tentative in range(1, Config.GEMINI_TENTATIVES + 1):
        try:
            reponse = client.models.generate_content(
                model=modele, contents=[piece, CONSIGNE], config=config)
            brut = (reponse.text or "").strip()
            if not brut:
                raise ValueError("reponse vide du modele")
            try:
                return json.loads(brut)
            except json.JSONDecodeError as exc:
                raise ValueError(f"reponse non JSON : {brut[:200]}") from exc
        except ValueError:
            raise
        except Exception as exc:
            derniere = exc
            if tentative >= Config.GEMINI_TENTATIVES:
                break
            attente = 2 * (3 ** (tentative - 1))   # 2 s puis 6 s
            logger.warning(
                "[ATTENTION] %s : tentative %d/%d echouee (%s), reprise dans %d s.",
                chemin.name, tentative, Config.GEMINI_TENTATIVES,
                type(exc).__name__, attente)
            time.sleep(attente)

    raise TimeoutError(
        f"{Config.GEMINI_TENTATIVES} tentatives echouees sur {chemin.name} "
        f"(timeout {timeout_ms} ms) : {derniere}")


def _normaliser(donnees: dict[str, Any], chemin: Path, modele: str) -> dict[str, Any]:
    """
    Met la reponse du modele au format de achat.facture_fournisseur.

    Applique les deux garanties que le schema SQL exige : une note de credit est
    stockee en negatif, et les PO sont completes a 8 chiffres.
    """
    type_piece = str(donnees.get("type_piece") or "facture").strip().lower()
    if type_piece not in TYPES_PIECE:
        type_piece = "facture"

    montant = donnees.get("montant")
    if montant is not None:
        montant = float(montant)
        # Le modele peut rendre une note de credit en positif malgre la
        # consigne. On corrige ici plutot que de laisser la contrainte SQL
        # rejeter la ligne : la piece existe, son signe est une convention.
        if type_piece == "note_credit" and montant > 0:
            logger.info("[INFO] %s : note de credit rendue en positif, signe corrige.",
                        chemin.name)
            montant = -montant

    pos = [str(p).strip().zfill(8) for p in (donnees.get("po_numbers") or [])
           if str(p).strip()]

    return {
        "n_facture": donnees.get("n_facture") or None,
        "fournisseur": donnees.get("fournisseur") or None,
        "type_piece": type_piece,
        "date_piece": donnees.get("date_piece") or None,
        "montant": montant,
        "montant_ht": donnees.get("montant_ht"),
        "devise": (donnees.get("devise") or None),
        "po_numbers": pos or None,
        "n_conteneur": donnees.get("n_conteneur") or None,
        "n_bl": donnees.get("n_bl") or None,
        "source_fichier": chemin.name,
        "methode_extraction": f"llm:{modele}",
        "confiance": float(donnees.get("confiance") or 0.0),
        "texte_source": donnees.get("libelle_montant_lu") or None,
        "commentaire": donnees.get("commentaire") or None,
    }


def parse_facture(chemin: Path, client: Any = None) -> Optional[dict[str, Any]]:
    """
    Extrait une piece comptable d'un fichier, ou None si ce n'en est pas une.

    Escalade sur le modele lourd quand la confiance du premier passage est sous
    le seuil : la majorite des factures sont lisibles et n'ont pas besoin de
    payer le modele le plus cher, mais un scan de travers merite un second avis.

    Args:
        chemin: PDF ou image a analyser.
        client: client Gemini reutilisable (evite une instanciation par PJ).
    Returns:
        Dictionnaire pret pour achat.facture_fournisseur, ou None si le document
        n'est pas une piece comptable.
    Raises:
        RuntimeError: extraction indisponible (SDK ou cle manquants).
    """
    if chemin.suffix.lower() not in EXTENSIONS_SUPPORTEES:
        logger.info("[INFO] %s ignore : extension non traitable.", chemin.name)
        return None

    client = client or _client_gemini()
    donnees = _appel_modele(client, chemin, Config.MODELE_FACTURE)
    modele_utilise = Config.MODELE_FACTURE

    if not donnees.get("est_piece_comptable"):
        logger.info("[INFO] %s : pas une piece comptable, ignore.", chemin.name)
        return None

    confiance = float(donnees.get("confiance") or 0.0)
    if confiance < Config.SEUIL_CONFIANCE_FACTURE:
        logger.warning("[ATTENTION] %s : confiance %.2f sous le seuil %.2f, "
                       "escalade sur %s.", chemin.name, confiance,
                       Config.SEUIL_CONFIANCE_FACTURE, Config.MODELE_FACTURE_ESCALADE)
        try:
            secondes = _appel_modele(client, chemin, Config.MODELE_FACTURE_ESCALADE)
            if secondes.get("est_piece_comptable"):
                donnees, modele_utilise = secondes, Config.MODELE_FACTURE_ESCALADE
        except Exception as exc:
            # L'escalade est un bonus : son echec ne doit pas perdre le premier
            # resultat, meme imparfait. Il partira simplement a valider.
            logger.warning("[ATTENTION] %s : escalade impossible (%s), "
                           "conservation du premier passage.", chemin.name, exc)

    resultat = _normaliser(donnees, chemin, modele_utilise)
    logger.info("[SUCCES] %s -> %s %s %s (confiance %.2f, PO %s)",
                chemin.name, resultat["type_piece"], resultat["montant"],
                resultat["devise"], resultat["confiance"], resultat["po_numbers"])
    return resultat


def parse_dossier(dossier: Path, tri: Optional[bool] = None) -> list[dict[str, Any]]:
    """
    Analyse recursivement un dossier de pieces jointes.

    Args:
        dossier: racine des PJ telechargees par fetch_attachments.py.
        tri: force le tri prealable. None = valeur de Config.TRI_PREALABLE_PIECE.
            Mettre False sert au test de non-regression du tri : on repasse tout
            au modele et on compare ses verdicts a ceux du tri.
    Returns:
        Pieces comptables normalisees, pretes pour achat.facture_fournisseur.
    Raises:
        RuntimeError: extraction indisponible, ou coupe-circuit de lot declenche.
    """
    from src.scripts.gmail.triage_piece import trier_dossier

    if Config.TRI_PREALABLE_PIECE if tri is None else tri:
        a_analyser, ecartes = trier_dossier(dossier)
        for fichier, verdict in ecartes:
            logger.info("[TRI] %s ecarte sans appel modele (%s : %s).",
                        fichier.name, verdict.etage, verdict.motif)
    else:
        a_analyser = [p for p in sorted(dossier.rglob("*"))
                      if p.is_file() and p.suffix.lower() in EXTENSIONS_SUPPORTEES]
        logger.warning("[ATTENTION] Tri prealable desactive : les %d piece(s) "
                       "partent toutes au modele.", len(a_analyser))

    client = _client_gemini()
    resultats: list[dict[str, Any]] = []
    # Coupe-circuit : on ne compte que les TimeoutError, seules a couter cher.
    # Une reponse non JSON echoue en une seconde et n'annonce pas une panne d'API,
    # alors qu'une serie de timeouts signifie que le service ne repond plus et que
    # continuer ferait tourner la tache planifiee des heures pour rien.
    timeouts_consecutifs = 0
    for fichier in a_analyser:
        try:
            piece = parse_facture(fichier, client=client)
            timeouts_consecutifs = 0
            if piece:
                resultats.append(piece)
        except RuntimeError:
            raise
        except TimeoutError as exc:
            timeouts_consecutifs += 1
            logger.error("[ECHEC] %s : %s", fichier.name, exc)
            if timeouts_consecutifs >= Config.GEMINI_ECHECS_CONSECUTIFS_MAX:
                raise RuntimeError(
                    f"{timeouts_consecutifs} timeouts consecutifs : le service "
                    f"Gemini ne repond plus, lot interrompu apres "
                    f"{len(resultats)} piece(s) extraite(s). Relancer le lot "
                    "quand le service repond, l'extraction est idempotente."
                ) from exc
        except Exception as exc:
            logger.error("[ECHEC] %s : %s", fichier.name, exc)
    return resultats


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s -- %(message)s")
    ap = argparse.ArgumentParser(
        description="Extraction des montants de facture depuis les PJ Gmail.")
    ap.add_argument("--file", type=str, help="Une piece jointe.")
    ap.add_argument("--folder", type=str, help="Dossier de PJ (recursif).")
    ap.add_argument("--out", type=str, default="", help="Fichier JSON de sortie.")
    ap.add_argument("--sans-tri", action="store_true",
                    help="Desactive le tri prealable et envoie TOUTES les pieces "
                         "au modele. Sert au test de non-regression du tri : "
                         "aucun document ecarte par le tri ne doit avoir ete "
                         "retenu par le modele.")
    args = ap.parse_args()

    if args.file:
        # Le tri ne s'applique pas a --file : demander explicitement l'analyse
        # d'un fichier precis est une action humaine, qui doit toujours aboutir.
        piece = parse_facture(Path(args.file))
        resultats = [piece] if piece else []
    elif args.folder:
        resultats = parse_dossier(Path(args.folder),
                                  tri=False if args.sans_tri else None)
    else:
        ap.error("Fournir --file ou --folder.")
        return 2

    charge = json.dumps(resultats, ensure_ascii=False, indent=2, default=str)
    if args.out:
        Path(args.out).write_text(charge, encoding="utf-8")
        logger.info("[SUCCES] %d piece(s) -> %s", len(resultats), args.out)
    else:
        # print assume : sortie de DONNEES du CLI, redirigeable (| jq, > fichier).
        # Les logs partent sur stderr via logger, comme dans parse_bl.py.
        print(charge)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
