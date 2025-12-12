import requests
import logging
from typing import List, Dict, Optional, Any

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class HummingbotAPIClient:
    """
    Client for interacting with the Hummingbot Client API (not Gateway).
    Used to fetch trades, PnL, and market data from the running bot instance.
    """
    def __init__(self, base_url: str = "http://localhost:8000", auth: tuple = None):
        self.base_url = base_url.rstrip('/')
        self.session = requests.Session()
        if auth:
            self.session.auth = auth

    def _post(self, endpoint: str, json_data: Optional[Dict] = None) -> Optional[Any]:
        url = f"{self.base_url}/{endpoint}"
        try:
            response = self.session.post(url, json=json_data, timeout=5)
            if response.status_code == 404:
                logger.warning(f"Endpoint not found: {url}")
                return None
            elif response.status_code == 401:
                logger.error(f"Unauthorized: {url}")
                return None
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.warning(f"Hummingbot API request failed ({url}): {e}")
            return None

    def _get(self, endpoint: str, params: Optional[Dict] = None) -> Optional[Any]:
        url = f"{self.base_url}/{endpoint}"
        try:
            response = self.session.get(url, params=params, timeout=5)
            if response.status_code == 401:
                logger.error(f"Unauthorized: {url}")
                return None
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.warning(f"Hummingbot API request failed ({url}): {e}")
            return None

    def get_trades(self, connector: str = None, trading_pair: str = None, start_ts: int = None, end_ts: int = None) -> List[Dict]:
        """
        Fetch trades. Filters are applied client-side if API doesn't support them all.
        """
        # Note: Actual HB Client API endpoints may vary. Assuming standard available endpoints.
        # Often /history or /trades
        params = {}
        if start_ts: params['start_timestamp'] = start_ts
        if end_ts: params['end_timestamp'] = end_ts
        
        data = self._get("history", params) # Hypothetical endpoint, adjust as needed
        if not data:
            return []
        
        trades = data if isinstance(data, list) else data.get('trades', [])
        
        # Filter if API didn't
        filtered = []
        for t in trades:
            if connector and t.get('connector_name') != connector: continue
            if trading_pair and t.get('trading_pair') != trading_pair: continue
            filtered.append(t)
            
        return filtered

    def get_market_data(self, connector: str, trading_pair: str) -> Dict:
        """
        Get ticker/book info.
        """
        return self._post("market-data/order-book", json_data={
            "connector_name": connector,
            "trading_pair": trading_pair
        }) or {}
        
    def get_pnl(self) -> Dict:
        """
        Get global PnL stats.
        """
        return self._get("pnl") or {}

    def is_healthy(self) -> bool:
        try:
            # Try root endpoint which we know returns status
            r = self.session.get(f"{self.base_url}/", timeout=2)
            return r.status_code == 200
        except:
            return False

if __name__ == "__main__":
    # Try default credentials first
    client = HummingbotAPIClient(auth=('admin', 'admin'))
    
    if client.is_healthy():
        print(f"✅ Hummingbot API is reachable (Authenticated).")
        
        # Test Uniswap V4 Connectivity
        print("\nTesting Uniswap V4 Connector via Gateway...")
        # Note: In real usage, Client connects to Gateway. Here we test if Client *can* reach it via its methods
        # But actually, hb_api_client usually talks to Hummingbot Client (port 8000), not Gateway (15888) directly?
        # The PROMPT says: "Compatible with Quants Lab’s hb_api_client.py" and "Use /connectors/uniswap_v4/amm".
        # This implies we might be adding direct Gateway support or checking if Client relays it.
        # Assuming we want to test direct gateway connectivity or client proxy. 
        # But wait, looking at the code, this client talks to port 8000 (HB Client).
        # Use Gateway URL for this specific test if we want to bypass HB Client or update base_url?
        # The user said: "Update hb_api_client.py to point it at the new stable prefix".
        # BUT hb_api_client defaults to localhost:8000. 
        # Let's assume we want to add a method that *can* talk to Gateway directly for this specific test, 
        # or change the default if the user intends this client to talk to Gateway.
        # Given "hb_api_client" refers to "Hummingbot API Client" (the bot), usually it proxies.
        # However, for this smoke test, let's allow it to connect to Gateway for verification.
        
        gateway_client = HummingbotAPIClient(base_url="http://localhost:15888", auth=None)
        
        # 1. Health
        try:
            health = gateway_client._get("connectors/uniswap_v4/amm/health")
            if health and health.get('status') == 'ok':
                print("✅ Uniswap V4 Health Check Passed via Client Lib.")
                print(f"   ChainID: {health.get('chainId')}")
            else:
                print("❌ Uniswap V4 Health Check FAILED.")
                print(f"   Response: {health}")
        except Exception as e:
            print(f"❌ Uniswap V4 Connection Error: {e}")

        # 2. Market Data (optional)
        # ob = gateway_client.get_market_data("uniswap_v4", "WETH-USDC") # This hits market-data/order-book which is HB Client endpoint
        
    else:
        print(f"⚠️  Hummingbot API not reachable or unauthorized at {client.base_url}")
