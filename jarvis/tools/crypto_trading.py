import json
import os
from jarvis.observability.logger import get_logger
from jarvis.tools.base import Tool, ToolResult
from jarvis.tools.http_request import HttpRequestTool

log = get_logger("tools.crypto_trading")

class CryptoTradingTool(Tool):
    """Crypto trading simulation tool using CoinGecko data.

    Provides methods to get prices, generate signals, and simulate trades.
    """

    name = "crypto_trading"
    description = "Simulate crypto trading with CoinGecko data: get prices, signals, and trades."
    timeout_seconds = 30

    def __init__(self):
        self.http = HttpRequestTool()
        self.portfolio_file = "/app/data/crypto_portfolio.json"

    async def execute(self, action: str, **kwargs) -> ToolResult:
        if action == "get_prices":
            return await self.get_prices()
        elif action == "get_signals":
            return await self.get_signals()
        elif action == "simulate_trade":
            symbol = kwargs.get("symbol")
            side = kwargs.get("side")
            amount = kwargs.get("amount")
            if not all([symbol, side, amount is not None]):
                return ToolResult(success=False, output="", error="Missing parameters: symbol, side, amount")
            return await self.simulate_trade(symbol, side, float(amount))
        else:
            return ToolResult(success=False, output="", error=f"Invalid action: {action}")

    async def get_prices(self) -> ToolResult:
        """Get top 10 crypto prices from CoinGecko."""
        url = "https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&order=market_cap_desc&per_page=10&page=1&sparkline=false"
        result = await self.http.execute(url=url, method="GET", headers={"Accept": "application/json"})
        if not result.success:
            return ToolResult(success=False, output="", error=result.error)
        # Parse JSON
        parts = result.output.split("\n\n", 1)
        json_str = parts[1] if len(parts) > 1 else parts[0]
        try:
            data = json.loads(json_str)
            return ToolResult(success=True, output=json.dumps(data))
        except json.JSONDecodeError as e:
            return ToolResult(success=False, output="", error=f"JSON parse error: {e}")

    async def get_signals(self) -> ToolResult:
        """Generate trading signals based on 24h change and volume."""
        prices_result = await self.get_prices()
        if not prices_result.success:
            return prices_result
        data = json.loads(prices_result.output)
        signals = {}
        # Load portfolio
        if os.path.exists(self.portfolio_file):
            with open(self.portfolio_file, 'r') as f:
                portfolio = json.load(f)
        else:
            portfolio = {"USDT": 1000, "holdings": {}, "last_volumes": {}}
        last_volumes = portfolio.get("last_volumes", {})
        for coin in data:
            symbol = coin['symbol'].upper()
            change_24h = coin.get('price_change_percentage_24h', 0) or 0
            volume = coin.get('total_volume', 0) or 0
            last_vol = last_volumes.get(symbol, 0)
            volume_up = volume > last_vol if last_vol > 0 else True
            if change_24h > -2 and volume_up:
                signals[symbol] = "buy"
            elif change_24h < -5:
                signals[symbol] = "sell"
            else:
                signals[symbol] = "hold"
            # Update last_volumes
            last_volumes[symbol] = volume
        # Save
        portfolio["last_volumes"] = last_volumes
        with open(self.portfolio_file, 'w') as f:
            json.dump(portfolio, f)
        return ToolResult(success=True, output=json.dumps(signals))

    async def simulate_trade(self, symbol: str, side: str, amount: float) -> ToolResult:
        """Simulate a trade."""
        prices_result = await self.get_prices()
        if not prices_result.success:
            return prices_result
        data = json.loads(prices_result.output)
        price = None
        for coin in data:
            if coin['symbol'].upper() == symbol.upper():
                price = coin['current_price']
                break
        if price is None:
            return ToolResult(success=False, output="", error=f"Symbol {symbol} not found in top 10")
        # Load portfolio
        if os.path.exists(self.portfolio_file):
            with open(self.portfolio_file, 'r') as f:
                portfolio = json.load(f)
        else:
            portfolio = {"USDT": 1000, "holdings": {}, "last_volumes": {}}
        usdt = portfolio["USDT"]
        holdings = portfolio["holdings"]
        if side == "buy":
            cost = amount * price
            if usdt >= cost:
                usdt -= cost
                holdings[symbol] = holdings.get(symbol, 0) + amount
            else:
                return ToolResult(success=False, output="", error="Insufficient USDT")
        elif side == "sell":
            if holdings.get(symbol, 0) >= amount:
                usdt += amount * price
                holdings[symbol] -= amount
                if holdings[symbol] <= 0:
                    holdings.pop(symbol, None)
            else:
                return ToolResult(success=False, output="", error="Insufficient holdings")
        else:
            return ToolResult(success=False, output="", error="Invalid side: use 'buy' or 'sell'")
        portfolio["USDT"] = usdt
        portfolio["holdings"] = holdings
        with open(self.portfolio_file, 'w') as f:
            json.dump(portfolio, f)
        return ToolResult(success=True, output=f"Simulated {side} {amount} {symbol} at ${price:.2f}. Portfolio updated.")