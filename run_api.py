"""
[SCRIPT]
=============================================================================
LANCEMENT LOCAL - ERP ACHAT FUSEAU (uvicorn)
=============================================================================

Lancement local POC -- ERP Achat TB Groupe
Usage : python run_api.py
Host/port configures dans config/.env (API_HOST, API_PORT) -- defaut 127.0.0.1:5050.
"""
import uvicorn

from src.utils.config_manager import Config

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=Config.API_HOST,
        port=Config.API_PORT,
        reload=Config.API_RELOAD,  # API_RELOAD=1 dans .env pour le dev uniquement
        log_level="info",
    )
