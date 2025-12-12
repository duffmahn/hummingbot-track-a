import os

class GatewayRoutes:
    """
    Centralized definition of Gateway V3 CLMM routes.
    Supports environment variable overrides for each route key.
    """
    
    @property
    def CLMM_ROOT(self) -> str:
        return os.environ.get("GATEWAY_ROUTE_CLMM_ROOT", "/connectors/uniswap/clmm")

    @property
    def POOL_INFO(self) -> str:
        return os.environ.get("GATEWAY_ROUTE_POOL_INFO", f"{self.CLMM_ROOT}/poolInfo")

    @property
    def POSITION_INFO(self) -> str:
        return os.environ.get("GATEWAY_ROUTE_POSITION_INFO", f"{self.CLMM_ROOT}/positionInfo")

    @property
    def POSITIONS_OWNED(self) -> str:
        return os.environ.get("GATEWAY_ROUTE_POSITIONS_OWNED", f"{self.CLMM_ROOT}/positionsOwned")

    @property
    def QUOTE_POSITION(self) -> str:
        return os.environ.get("GATEWAY_ROUTE_QUOTE_POSITION", f"{self.CLMM_ROOT}/quotePosition")
    
    @property
    def QUOTE_SWAP(self) -> str:
        return os.environ.get("GATEWAY_ROUTE_QUOTE_SWAP", f"{self.CLMM_ROOT}/quoteSwap")

    @property
    def OPEN_POSITION(self) -> str:
        return os.environ.get("GATEWAY_ROUTE_OPEN_POSITION", f"{self.CLMM_ROOT}/openPosition")

    @property
    def ADD_LIQUIDITY(self) -> str:
        return os.environ.get("GATEWAY_ROUTE_ADD_LIQUIDITY", f"{self.CLMM_ROOT}/addLiquidity")

    @property
    def REMOVE_LIQUIDITY(self) -> str:
        return os.environ.get("GATEWAY_ROUTE_REMOVE_LIQUIDITY", f"{self.CLMM_ROOT}/removeLiquidity")

    @property
    def CLOSE_POSITION(self) -> str:
        return os.environ.get("GATEWAY_ROUTE_CLOSE_POSITION", f"{self.CLMM_ROOT}/closePosition")

    @property
    def COLLECT_FEES(self) -> str:
        return os.environ.get("GATEWAY_ROUTE_COLLECT_FEES", f"{self.CLMM_ROOT}/collectFees")
    
    @property
    def EXECUTE_SWAP(self) -> str:
        return os.environ.get("GATEWAY_ROUTE_EXECUTE_SWAP", f"{self.CLMM_ROOT}/executeSwap")

GATEWAY_ROUTES = GatewayRoutes()
