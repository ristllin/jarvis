"""
CoinGecko cryptocurrency tool — provides access to CoinGecko API for crypto data.
Features: get top cryptocurrencies, get coin data by ID, get price data and 24h changes.
API docs: https://www.coingecko.com/api/documentation
"""
import json
from typing import Optional
from jarvis.tools.base import Tool, ToolResult
from jarvis.tools.http_request import HttpRequestTool
from jarvis.observability.logger import get_logger

log = get_logger("tools.coingecko")

BASE_URL = "https://api.coingecko.com/api/v3"


class CoinGeckoTool(Tool):
    """CoinGecko cryptocurrency data tool.

    Provides access to the CoinGecko public API for:
    - Top cryptocurrencies by market cap
    - Detailed coin data by ID
    - Price data with 24h changes
    """

    name = "coingecko"
    description = (
        "Get cryptocurrency data from CoinGecko API. Features: get top cryptocurrencies "
        "by market cap, get coin data by ID, get price data and 24h changes. "
        "Use for: crypto research, price tracking, market analysis."
    )
    timeout_seconds = 30

    def __init__(self):
        self.http = HttpRequestTool()

    async def execute(
        self,
        action: str,
        coin_id: Optional[str] = None,
        vs_currency: str = "usd",
        limit: int = 10,
        **kwargs,
    ) -> ToolResult:
        """
        Execute CoinGecko API actions.

        Args:
            action: One of: "top", "coin_data", "price"
            coin_id: Coin ID (e.g. "bitcoin"). Required for "coin_data" and "price".
            vs_currency: Currency to compare against (default: usd)
            limit: Number of results to return for "top" action (default: 10, max: 250)

        Returns:
            ToolResult with formatted cryptocurrency data.
        """
        # Validate action
        valid_actions = ("top", "coin_data", "price")
        if action not in valid_actions:
            return ToolResult(
                success=False,
                output="",
                error=f"Unknown action: {action}. Use one of: {', '.join(valid_actions)}",
            )

        # Validate coin_id for actions that require it
        if action in ("coin_data", "price") and not coin_id:
            return ToolResult(
                success=False,
                output="",
                error=f"coin_id is required for '{action}' action",
            )

        try:
            if action == "top":
                return await self._get_top_cryptos(vs_currency, limit)
            elif action == "coin_data":
                return await self._get_coin_data(coin_id, vs_currency)
            elif action == "price":
                return await self._get_price_data(coin_id, vs_currency)
        except Exception as e:
            log.error("coingecko_error", action=action, error=str(e))
            return ToolResult(success=False, output="", error=str(e))

    async def _api_get(self, url: str) -> ToolResult:
        """Make a GET request to the CoinGecko API via HttpRequestTool."""
        return await self.http.execute(
            url=url,
            method="GET",
            headers={"Accept": "application/json"},
        )

    def _parse_json_response(self, result: ToolResult) -> dict | list | None:
        """Extract and parse JSON from an HttpRequestTool response.

        The http_request tool returns headers + body separated by a blank line.
        We split on the first blank line to get the JSON body.
        """
        if not result.success:
            return None
        raw = result.output
        # Find the blank line separating headers from body
        parts = raw.split("\n\n", 1)
        json_str = parts[1] if len(parts) > 1 else parts[0]
        return json.loads(json_str)

    async def _get_top_cryptos(self, vs_currency: str, limit: int) -> ToolResult:
        """Get top cryptocurrencies by market cap."""
        capped_limit = max(1, min(limit, 250))  # API max is 250
        url = (
            f"{BASE_URL}/coins/markets"
            f"?vs_currency={vs_currency}"
            f"&order=market_cap_desc"
            f"&per_page={capped_limit}"
            f"&page=1"
            f"&sparkline=false"
        )

        result = await self._api_get(url)
        if not result.success:
            return ToolResult(success=False, output="", error=f"API request failed: {result.error}")

        try:
            data = self._parse_json_response(result)
            if not isinstance(data, list):
                return ToolResult(success=False, output="", error="Unexpected API response format")

            lines = []
            for i, coin in enumerate(data, 1):
                name = coin.get("name", "N/A")
                symbol = coin.get("symbol", "?").upper()
                price = coin.get("current_price", 0) or 0
                mcap = coin.get("market_cap", 0) or 0
                change = coin.get("price_change_percentage_24h", 0) or 0
                lines.append(
                    f"{i}. {name} ({symbol}): "
                    f"${price:,.2f} | "
                    f"MCap: ${mcap:,.0f} | "
                    f"24h: {change:+.2f}%"
                )

            header = f"Top {len(data)} Cryptocurrencies by Market Cap ({vs_currency.upper()})\n"
            return ToolResult(success=True, output=header + "\n".join(lines))

        except (json.JSONDecodeError, ValueError) as e:
            return ToolResult(success=False, output="", error=f"Failed to parse response: {e}")

    async def _get_coin_data(self, coin_id: str, vs_currency: str) -> ToolResult:
        """Get detailed data for a specific coin."""
        url = (
            f"{BASE_URL}/coins/{coin_id}"
            f"?localization=false"
            f"&tickers=false"
            f"&community_data=false"
            f"&developer_data=false"
        )

        result = await self._api_get(url)
        if not result.success:
            return ToolResult(success=False, output="", error=f"API request failed: {result.error}")

        try:
            data = self._parse_json_response(result)
            if not isinstance(data, dict):
                return ToolResult(success=False, output="", error="Unexpected API response format")

            name = data.get("name", "N/A")
            symbol = data.get("symbol", "?").upper()
            description_text = data.get("description", {}).get("en", "No description available.")
            # Truncate description
            if len(description_text) > 300:
                description_text = description_text[:300] + "..."

            market_data = data.get("market_data", {})
            price = market_data.get("current_price", {}).get(vs_currency, 0) or 0
            mcap = market_data.get("market_cap", {}).get(vs_currency, 0) or 0
            volume = market_data.get("total_volume", {}).get(vs_currency, 0) or 0
            high_24h = market_data.get("high_24h", {}).get(vs_currency, 0) or 0
            low_24h = market_data.get("low_24h", {}).get(vs_currency, 0) or 0
            change_24h = market_data.get("price_change_percentage_24h", 0) or 0
            ath = market_data.get("ath", {}).get(vs_currency, 0) or 0
            circulating = market_data.get("circulating_supply", 0) or 0
            total_supply = market_data.get("total_supply", 0)

            supply_str = f"{circulating:,.0f}"
            if total_supply:
                supply_str += f" / {total_supply:,.0f}"

            output = (
                f"{name} ({symbol})\n"
                f"{'=' * 40}\n"
                f"Price:            ${price:,.2f}\n"
                f"24h Change:       {change_24h:+.2f}%\n"
                f"24h High/Low:     ${high_24h:,.2f} / ${low_24h:,.2f}\n"
                f"Market Cap:       ${mcap:,.0f}\n"
                f"24h Volume:       ${volume:,.0f}\n"
                f"All-Time High:    ${ath:,.2f}\n"
                f"Supply:           {supply_str}\n"
                f"{'=' * 40}\n"
                f"Description: {description_text}"
            )
            return ToolResult(success=True, output=output)

        except (json.JSONDecodeError, ValueError) as e:
            return ToolResult(success=False, output="", error=f"Failed to parse response: {e}")

    async def _get_price_data(self, coin_id: str, vs_currency: str) -> ToolResult:
        """Get price and 24h change data for a specific coin."""
        url = (
            f"{BASE_URL}/simple/price"
            f"?ids={coin_id}"
            f"&vs_currencies={vs_currency}"
            f"&include_24hr_change=true"
            f"&include_market_cap=true"
            f"&include_24hr_vol=true"
        )

        result = await self._api_get(url)
        if not result.success:
            return ToolResult(success=False, output="", error=f"API request failed: {result.error}")

        try:
            data = self._parse_json_response(result)
            if not isinstance(data, dict) or coin_id not in data:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Coin '{coin_id}' not found. Check the coin ID.",
                )

            coin_data = data[coin_id]
            price = coin_data.get(vs_currency, 0) or 0
            change_24h = coin_data.get(f"{vs_currency}_24h_change", 0) or 0
            mcap = coin_data.get(f"{vs_currency}_market_cap", 0) or 0
            volume = coin_data.get(f"{vs_currency}_24h_vol", 0) or 0

            output = (
                f"{coin_id.title()} ({vs_currency.upper()})\n"
                f"Price:      ${price:,.2f}\n"
                f"24h Change: {change_24h:+.2f}%\n"
                f"Market Cap: ${mcap:,.0f}\n"
                f"24h Volume: ${volume:,.0f}"
            )
            return ToolResult(success=True, output=output)

        except (json.JSONDecodeError, ValueError) as e:
            return ToolResult(success=False, output="", error=f"Failed to parse response: {e}")

    def get_schema(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "action": {
                    "type": "string",
                    "description": (
                        "Action to perform: 'top' (top cryptos by market cap), "
                        "'coin_data' (detailed coin info), 'price' (price + 24h change)"
                    ),
                    "enum": ["top", "coin_data", "price"],
                },
                "coin_id": {
                    "type": "string",
                    "description": (
                        "CoinGecko coin ID (e.g. 'bitcoin', 'ethereum', 'solana'). "
                        "Required for 'coin_data' and 'price' actions."
                    ),
                },
                "vs_currency": {
                    "type": "string",
                    "description": "Currency to compare against (default: 'usd'). Examples: usd, eur, gbp, btc.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Number of results for 'top' action (default: 10, max: 250)",
                },
            },
            "required": ["action"],
        }
