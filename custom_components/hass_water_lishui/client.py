"""HTTP client for the Lishui Water (丽水供排水) WeChat API.

This module imports nothing from Home Assistant, so it can be exercised
standalone (load it by path, the package itself does need Home Assistant)::

    import asyncio, importlib.util, pathlib

    import aiohttp

    path = pathlib.Path("custom_components/hass_water_lishui/client.py")
    spec = importlib.util.spec_from_file_location("lishui_client", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    async def main() -> None:
        async with aiohttp.ClientSession() as session:
            client = module.LishuiWaterClient(session, card_no="123456", year="2026")
            print(await client.async_fetch_fares())

    asyncio.run(main())
"""

from __future__ import annotations

import logging
from typing import Any

from aiohttp import ClientError, ClientSession

# Kept here (not in const.py) on purpose: const.py imports homeassistant.const,
# and this module must stay importable without Home Assistant so the parsing
# logic can be exercised standalone.
DEFAULT_API_BASE = "http://wx.lswater.cn"
API_TIMEOUT = 15

_LOGGER = logging.getLogger(__name__)

# The upstream service is a WeChat mini-program web backend; it only serves
# requests carrying the mini-program User-Agent / Appid headers.
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36 NetType/WIFI "
    "MicroMessenger/7.0.20.1781(0x6700143B) WindowsWechat(0x63090a13) "
    "UnifiedPCWindowsWechat(0xf2540510) XWEB/13871 Flue"
)

# Codes the service uses for an expired / invalid token.
_AUTH_CODES = {"401", "403"}


class LishuiWaterApiError(Exception):
    """Base API error."""


class LishuiWaterAuthError(LishuiWaterApiError):
    """Token authentication related error."""


class LishuiWaterNoDataError(LishuiWaterApiError):
    """The API answered, but there is no billing record for this meter/year."""


class LishuiWaterClient:
    """Client for the Lishui water fee API."""

    def __init__(
        self,
        session: ClientSession,
        card_no: str,
        year: str,
        token: str = "",
    ) -> None:
        """Initialize the client.

        Args:
            session: aiohttp session injected by the caller.
            card_no: Water meter card number (also used as clientNo).
            year: Billing year to query, e.g. "2026".
            token: Optional mini-program token for authenticated fields.
        """
        self._session = session
        self._card_no = card_no
        self._year = year
        self._token = token

    async def async_fetch_fares(self) -> list[dict[str, Any]]:
        """Fetch the bill list from the remote API.

        Returns a list of bill dicts with keys such as ``fareMonth``,
        ``balance``, ``fareValue``, ``currDegree``, ``lastDegree``,
        ``currCopyDate``, ``lastCopyDate`` and ``billFlag`` (0 == paid).
        """
        url = f"{DEFAULT_API_BASE}/upfscapi/wxClient/getFareList"
        headers = {
            "User-Agent": _USER_AGENT,
            "Accept": "application/json, text/plain, */*",
            "Accept-Encoding": "gzip, deflate",
            "Appid": "70000",
            "Token": self._token,
            "Referer": "http://wx.lswater.cn/upfscwx",
            "Accept-Language": "zh-CN,zh;q=0.9",
        }
        params = {
            "cardNo": self._card_no,
            "clientNo": self._card_no,
            "year": self._year,
        }

        try:
            async with self._session.get(
                url,
                headers=headers,
                params=params,
                timeout=API_TIMEOUT,
            ) as response:
                payload = await response.json(content_type=None)
        except (TimeoutError, ClientError) as err:
            raise LishuiWaterApiError(f"HTTP error: {err}") from err
        except ValueError as err:
            raise LishuiWaterApiError("Invalid JSON response") from err

        if not isinstance(payload, dict):
            raise LishuiWaterApiError("Unexpected response format")

        code = str(payload.get("code", ""))
        if code != "00":
            # Never log the token or the whole payload; the message alone is
            # enough for users to report issues.
            message = str(payload.get("message") or "Unknown API error")
            if code in _AUTH_CODES or "token" in message.lower():
                raise LishuiWaterAuthError(message)
            raise LishuiWaterApiError(f"API error code={code}: {message}")

        data = payload.get("data")
        if not isinstance(data, list):
            raise LishuiWaterApiError("API response data is not a list")
        return data
