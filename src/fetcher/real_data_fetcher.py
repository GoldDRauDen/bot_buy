"""
Real Data Fetcher - Fetch gia that tu vietstock cho watchlist.
PHA 2: Nguon du lieu that da xac nhan (recon):
  https://finance.vietstock.vn/{SYMBOL}/thong-ke-giao-dich.htm
  -> var _stockTrade = {...JSON...} (ClosePrice, TotalVol, PerChange, TradingDate...)

Khong bia so lieu: chi ghi du lieu parse duoc tu HTML that.
Loi/khong parse duoc -> bo qua ma do, ghi loi.
"""
import json
import logging
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from requests.exceptions import RequestException, Timeout, SSLError

try:
    from ..utils.config_loader import load_settings
except ImportError:
    from utils.config_loader import load_settings


VIETSTOCK_URL = "https://finance.vietstock.vn/{symbol}/thong-ke-giao-dich.htm"
USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")


def _strip_html(value: str) -> str:
    """Bo the HTML va entities khoi chuoi."""
    value = re.sub(r"<[^>]+>", "", value)
    return value.strip()


def _extract_json_object(text: str, marker: str) -> Optional[str]:
    """
    Trich JSON object bat dau sau marker bang brace-counting (chong cat ngang
    khi JSON chua dau {} trong chuoi). Tra raw JSON string hoac None.
    """
    start = text.find(marker)
    if start < 0:
        return None
    start += len(marker)
    depth = 0
    in_str = False
    escape = False
    for i in range(start, len(text)):
        c = text[i]
        if escape:
            escape = False
            continue
        if c == "\\":
            escape = True
            continue
        if c == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    return None


def _parse_stock_trade(html: str) -> Optional[Dict[str, Any]]:
    """Parse _stockTrade JSON tu HTML. Tra None neu khong co."""
    raw = _extract_json_object(html, "var _stockTrade=")
    if raw is None:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    return data


class RealDataFetcher:
    """Fetch gia that cho watchlist tu vietstock."""

    def __init__(self, logger: logging.Logger = None, base_dir: Path = None,
                 config: Dict[str, Any] = None):
        self.logger = logger or logging.getLogger("real_data_fetcher")
        if base_dir is None:
            base_dir = Path(__file__).parent.parent.parent
        self.base_dir = Path(base_dir)
        self.output_dir = self.base_dir / "output"
        self.real_data_dir = self.output_dir / "real_data"

        if config is None:
            try:
                settings = load_settings()
                config = settings.get("ai", {})
            except Exception:
                config = {}
        self.config = config or {}
        self.watchlist = self.config.get("watchlist", []) or []
        if not self.watchlist:
            self.watchlist = ["ACB", "VCB", "BID", "FPT", "HPG", "VNM",
                              "VIC", "VHM", "GAS", "VPB"]
        self.timeout = int(self.config.get("timeout", 15))
        self.retries = int(self.config.get("retries", 2))
        self.request_delay = float(self.config.get("request_delay", 0.5))
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})
        self._ssl_verify_cache: Dict[str, bool] = {}

    def _fetch_page(self, symbol: str) -> Optional[str]:
        """GET trang vietstock cho symbol. Tra HTML hoac None."""
        url = VIETSTOCK_URL.format(symbol=symbol)
        verify = self._ssl_verify_cache.get("finance.vietstock.vn", True)
        for attempt in range(self.retries + 1):
            try:
                resp = self.session.get(url, timeout=self.timeout, verify=verify)
                if resp.status_code == 200:
                    return resp.text
                self.logger.warning(f"vietstock {symbol} -> {resp.status_code} (lan {attempt + 1})")
            except SSLError:
                self._ssl_verify_cache["finance.vietstock.vn"] = False
                verify = False
            except (Timeout, RequestException) as e:
                self.logger.warning(f"vietstock {symbol} loi (lan {attempt + 1}): {e}")
            if attempt < self.retries:
                time.sleep(1.0 * (attempt + 1))
        return None

    @staticmethod
    def _extract_price(html_or_plain: str) -> str:
        """Lay gia tu chuoi co the chua HTML span."""
        return _strip_html(html_or_plain)

    def fetch_symbol(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Fetch 1 symbol, parse _stockTrade.
        Tra dict {symbol, price, change, change_percent, volume, open, high,
                  low, trading_date, fetched_at, source_url} hoac None.
        """
        html = self._fetch_page(symbol)
        if html is None:
            return None
        data = _parse_stock_trade(html)
        if data is None:
            self.logger.warning(f"Khong parse duoc _stockTrade cho {symbol}")
            return None

        # Extract gia tri (co the chua HTML)
        last = self._extract_price(data.get("LastPrice") or data.get("ClosePrice") or "")
        close = self._extract_price(data.get("ClosePrice") or "")
        change = self._extract_price(data.get("Change") or "")
        pct = self._extract_price(data.get("PerChange") or "")
        total_vol = self._extract_price(data.get("TotalVol") or "")
        open_p = self._extract_price(data.get("OpenPrice") or "")
        high = self._extract_price(data.get("HighestPrice") or "")
        low = self._extract_price(data.get("LowestPrice") or "")
        date = self._extract_price(data.get("TradingDate") or "")

        if not last and not close:
            self.logger.warning(f"{symbol}: khong co gia (LastPrice/ClosePrice rong)")
            return None

        return {
            "symbol": symbol,
            "price": close or last,
            "change": change,
            "change_percent": pct,
            "volume": total_vol,
            "open": open_p,
            "high": high,
            "low": low,
            "trading_date": date,
            "fetched_at": datetime.now().isoformat(),
            "source_url": VIETSTOCK_URL.format(symbol=symbol),
        }

    def run(self) -> Dict[str, Any]:
        """Fetch toan bo watchlist, luu real_data/prices.json."""
        prices = []
        errors = []
        for symbol in self.watchlist:
            self.logger.info(f"Fetch {symbol}...")
            result = self.fetch_symbol(symbol)
            if result:
                prices.append(result)
            else:
                errors.append({"symbol": symbol, "error": "fetch/parse failed"})
            time.sleep(self.request_delay)

        report = {
            "generated_at": datetime.now().isoformat(),
            "source": "vietstock _stockTrade (https://finance.vietstock.vn/{symbol}/thong-ke-giao-dich.htm)",
            "watchlist_size": len(self.watchlist),
            "fetched_count": len(prices),
            "error_count": len(errors),
            "errors": errors,
            "prices": prices,
        }
        self.save_report(report)
        return report

    def save_report(self, report: Dict[str, Any], output_path: str = None) -> str:
        if output_path is None:
            output_path = self.output_dir / "real_data" / "prices.json"
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        self.logger.info(f"Da luu: {output_path}")
        return str(output_path)


def run_real_data_fetch(logger: logging.Logger = None) -> Dict[str, Any]:
    """Fetch gia that. Ham tien ich cho main.py / send_telegram.py."""
    if logger is None:
        logger = logging.getLogger("stock_scanner")
    fetcher = RealDataFetcher(logger=logger)
    report = fetcher.run()
    n = report.get("fetched_count", 0)
    err = report.get("error_count", 0)
    print(f"\n  Du lieu that: {n}/{report.get('watchlist_size', 0)} ma OK, {err} loi")
    for p in report.get("prices", [])[:3]:
        print(f"    - {p['symbol']}: {p['price']} ({p['change_percent']}) vol={p['volume']} {p['trading_date']}")
    return report
