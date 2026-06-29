# Règles AiOps — Projet FUSEAU (Data-Achat)

Ce document unifie les règles de développement, d'architecture et de déploiement pour les assistants IA (Antigravity/Claude) intervenant sur le projet FUSEAU.

## 1. Contexte Réseau & Infrastructure (Règles Sandbox)
- **Le VPN Stormshield est obligatoire** pour toute communication avec le DWH Azure (`172.31.2.4` ou `psql-dtpf-psql-prod`).
- **Sandbox Handoff :** Les sandboxes Linux des agents de dev n'ont PAS de route VPN active. Toutes les commandes SQL ou scripts d'intégration de données doivent être générés pour être **exécutés via le terminal local Windows** (MCP ou PowerShell).
- **DNS/Routing :** Ne pas modifier la configuration DNS globale ; privilégier la résolution locale ou les routes manuelles via le VPN.

## 2. Standards de Code (Python 3.11)
- **Typage statique obligatoire :** Toutes les fonctions doivent être typées pour les arguments et les valeurs de retour.
  * *Exemple :* `def execute_pipeline(df: pd.DataFrame) -> dict:`
- **Pas de Key Vault chez Marlène :** 
  * Sur le poste d'Antho : utilisation possible de `DefaultAzureCredential` pour lire Key Vault.
  * Sur le poste de Marlène : `KEY_VAULT_NAME` reste vide. Les accès se font via les variables d'environnement lues par la classe `Config` (`config/.env`).
- **Gestion des logs :** Bannir les simples `print()`. Utiliser le module `logging` standard avec des logs clairs (`[INFO]`, `[SUCCÈS]`, `[ERREUR]`).

## 3. Sécurité & Gestion Git (Règles Commits)
- **Fichiers strictement exclus (gitignoring) :**
  * `config/.env` (variables d'environnement et mots de passe)
  * `config/credentials.json` (OAuth GCP)
  * `config/token.json` (Cache OAuth)
  * Fichiers de cache python (`__pycache__`, `.pytest_cache`)
- **Messages de commits :** Toujours rédiger des messages de commit purement professionnels (pas de mention automatique "généré par IA").

## 4. Double Circuit d'Exécution (Déploiement)
- **Circuit A (Nouveau produit Import / Artworks) :** Utilise le connecteur Gmail pour l'extraction et l'analyse. L'écriture se fait en UPSERT sur `achat.commande`.
- **Circuit B (Réapprovisionnement) :** Analyse automatisée et dashboard en temps réel.
- **Grants BDD :** Le rôle `platform_team` a les privilèges de lecture (`SELECT`), ainsi que d'écriture (`INSERT`, `UPDATE`) sur `achat.commande` et ses tables associées. Il n'a aucun droit destructeur (`TRUNCATE`, `DROP`).
