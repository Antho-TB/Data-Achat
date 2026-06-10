"""
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
        reload=True,  # hot-reload en POC
        log_level="info",
    )
