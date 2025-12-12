import os
import time
import requests
from typing import Dict, Any, Optional

from .gateway_routes import GATEWAY_ROUTES

class GatewayCLMMClient:
    """
    Client for Hummingbot Gateway Uniswap V3 CLMM endpoints.
    Returns standard envelope: {success, data, error, latency_ms}
    """
    
    def __init__(self, base_url: Optional[str] = None, timeout: int = 30):
        self.base_url = base_url or os.environ.get("GATEWAY_URL", "https://localhost:15888")
        self.timeout = timeout
        self.cert_path = os.environ.get("GATEWAY_CERT_PATH")
        
    def _request(self, method: str, path: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Internal request wrapper with timing and error handling."""
        url = f"{self.base_url}{path}"
        start = time.time()
        
        try:
            kwargs = {
                "timeout": self.timeout,
                "json": payload,
            }
            
            # Add cert if available (for HTTPS)
            if self.cert_path and os.path.exists(self.cert_path):
                kwargs["verify"] = self.cert_path
            else:
                # In dev mode, might need to disable SSL verification
                kwargs["verify"] = False
                
            if method.upper() == "GET":
                response = requests.get(url, **kwargs)
            elif method.upper() == "POST":
                response = requests.post(url, **kwargs)
            else:
                raise ValueError(f"Unsupported method: {method}")
                
            latency_ms = (time.time() - start) * 1000
            
            response.raise_for_status()
            data = response.json()
            
            return {
                "success": True,
                "data": data,
                "error": None,
                "latency_ms": latency_ms
            }
            
        except requests.exceptions.RequestException as e:
            latency_ms = (time.time() - start) * 1000
            return {
                "success": False,
                "data": None,
                "error": str(e),
                "latency_ms": latency_ms
            }
    
    def pool_info(self, chain: str, network: str, connector: str, pool_address: str) -> Dict[str, Any]:
        """Get pool information."""
        payload = {
            "chain": chain,
            "network": network,
            "connector": connector,
            "address": pool_address
        }
        return self._request("POST", GATEWAY_ROUTES.POOL_INFO, payload)
    
    def position_info(self, chain: str, network: str, connector: str, token_id: int) -> Dict[str, Any]:
        """Get position information by token ID."""
        payload = {
            "chain": chain,
            "network": network,
            "connector": connector,
            "tokenId": token_id
        }
        return self._request("POST", GATEWAY_ROUTES.POSITION_INFO, payload)
    
    def positions_owned(self, chain: str, network: str, connector: str, address: str) -> Dict[str, Any]:
        """Get all positions owned by an address."""
        payload = {
            "chain": chain,
            "network": network,
            "connector": connector,
            "address": address
        }
        return self._request("POST", GATEWAY_ROUTES.POSITIONS_OWNED, payload)
    
    def quote_position(self, chain: str, network: str, connector: str, 
                      token0: str, token1: str, fee: str, 
                      lower_price: str, upper_price: str,
                      amount0: Optional[str] = None, amount1: Optional[str] = None) -> Dict[str, Any]:
        """Quote a position (simulate opening)."""
        payload = {
            "chain": chain,
            "network": network,
            "connector": connector,
            "token0": token0,
            "token1": token1,
            "fee": fee,
            "lowerPrice": lower_price,
            "upperPrice": upper_price
        }
        if amount0:
            payload["amount0"] = amount0
        if amount1:
            payload["amount1"] = amount1
            
        return self._request("POST", GATEWAY_ROUTES.QUOTE_POSITION, payload)
    
    def open_position(self, chain: str, network: str, connector: str,
                     address: str, token0: str, token1: str, fee: str,
                     lower_price: str, upper_price: str,
                     amount0: str, amount1: str) -> Dict[str, Any]:
        """Open a new position."""
        payload = {
            "chain": chain,
            "network": network,
            "connector": connector,
            "address": address,
            "token0": token0,
            "token1": token1,
            "fee": fee,
            "lowerPrice": lower_price,
            "upperPrice": upper_price,
            "amount0": amount0,
            "amount1": amount1
        }
        return self._request("POST", GATEWAY_ROUTES.OPEN_POSITION, payload)
    
    def close_position(self, chain: str, network: str, connector: str,
                      address: str, token_id: int) -> Dict[str, Any]:
        """Close an existing position."""
        payload = {
            "chain": chain,
            "network": network,
            "connector": connector,
            "address": address,
            "tokenId": token_id
        }
        return self._request("POST", GATEWAY_ROUTES.CLOSE_POSITION, payload)
    
    def add_liquidity(self, chain: str, network: str, connector: str,
                     address: str, token_id: int, 
                     amount0: str, amount1: str) -> Dict[str, Any]:
        """Add liquidity to existing position."""
        payload = {
            "chain": chain,
            "network": network,
            "connector": connector,
            "address": address,
            "tokenId": token_id,
            "amount0": amount0,
            "amount1": amount1
        }
        return self._request("POST", GATEWAY_ROUTES.ADD_LIQUIDITY, payload)
    
    def remove_liquidity(self, chain: str, network: str, connector: str,
                        address: str, token_id: int, 
                        decrease_percent: int) -> Dict[str, Any]:
        """Remove liquidity from position."""
        payload = {
            "chain": chain,
            "network": network,
            "connector": connector,
            "address": address,
            "tokenId": token_id,
            "decreasePercent": decrease_percent
        }
        return self._request("POST", GATEWAY_ROUTES.REMOVE_LIQUIDITY, payload)
    
    def collect_fees(self, chain: str, network: str, connector: str,
                    address: str, token_id: int) -> Dict[str, Any]:
        """Collect fees from position."""
        payload = {
            "chain": chain,
            "network": network,
            "connector": connector,
            "address": address,
            "tokenId": token_id
        }
        return self._request("POST", GATEWAY_ROUTES.COLLECT_FEES, payload)
    
    def health_check(self) -> Dict[str, Any]:
        """Check Gateway health."""
        try:
            return self._request("GET", "/")
        except Exception as e:
            return {
                "success": False,
                "data": None,
                "error": str(e),
                "latency_ms": 0.0
            }
