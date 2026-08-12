"""
Récupère le prix actuel du Bitcoin en euros via l'API publique de CoinGecko.
"""

import json
import sys
from urllib import request, error

def get_btc_price() -> float:
    """Retourne le prix du Bitcoin en EUR comme un float.
    Utilise l'endpoint public de CoinGecko.
    """
    api_url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=eur"
    try:
        with request.urlopen(api_url, timeout=10) as resp:
            if resp.status != 200:
                raise RuntimeError(f"HTTP error {resp.status}")
            data = json.loads(resp.read().decode())
            return float(data["bitcoin"]["eur"])
    except error.URLError as e:
        raise RuntimeError(f"Erreur réseau : {e}") from e
    except (KeyError, ValueError) as e:
        raise RuntimeError(f"Réponse inattendue : {e}") from e

if __name__ == "__main__":
    try:
        price = get_btc_price()
        print(f"{price:.2f}")
    except Exception as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)
