"""
AI Analyst - Goi Gemini API de phan tich du lieu that.
PHA 2: Phan tich DUNG SO lieu duoc cung cap, khong them so lieu khac.
Loi API hoac khong co du lieu -> tra None (khong bia).

Security: API key tu env GEMINI_API_KEY (CI: GitHub secrets).
"""
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

import requests

try:
    from ..utils.config_loader import load_settings
except ImportError:
    from utils.config_loader import load_settings


GEMINI_URL = ("https://generativelanguage.googleapis.com/v1beta/models/"
              "{model}:generateContent")
DEFAULT_MODEL = "gemini-2.0-flash"
FALLBACK_MODEL = "gemini-2.5-flash"


def build_prompt(prices_report: Dict[str, Any]) -> str:
    """
    Tao prompt phan tich tu prices.json.
    Chi dung so lieu co trong report.
    """
    prices = prices_report.get("prices", [])
    if not prices:
        return ""

    lines = [
        "Phân tích dữ liệu cổ phiếu Việt Nam dưới đây (dữ liệu THẬT từ vietstock, "
        "ngày giao dịch {date}):".format(date=prices[0].get("trading_date", "?")),
        "",
    ]
    for p in prices:
        lines.append(
            f"- {p.get('symbol')}: giá {p.get('price')} VND, "
            f"thay đổi {p.get('change_percent')}, "
            f"khối lượng {p.get('volume')}, "
            f"mở cửa {p.get('open')}, cao {p.get('high')}, thấp {p.get('low')}"
        )

    lines.append("")
    lines.append(
        "Yêu cầu: phân tích NGẮN GỌN bằng tiếng Việt (tối đa 400 từ): "
        "1) Tổng quan xu hướng thị trường; "
        "2) Biến động % nổi bật; "
        "3) Điểm đáng chú ý; "
        "4) Cảnh báo rủi ro. "
        "CHỈ dùng số liệu được cung cấp ở trên, KHÔNG thêm số liệu khác. "
        "Nếu thiếu dữ liệu, hãy nói rõ."
    )
    return "\n".join(lines)


class AiAnalyst:
    """Goi Gemini API phan tich."""

    def __init__(self, logger: logging.Logger = None, config: Dict[str, Any] = None):
        self.logger = logger or logging.getLogger("ai_analyst")
        if config is None:
            try:
                settings = load_settings()
                config = settings.get("ai", {})
            except Exception:
                config = {}
        self.config = config or {}
        self.model = self.config.get("model", DEFAULT_MODEL)
        self.timeout = int(self.config.get("timeout", 30))

    def analyze(self, prices_report: Dict[str, Any],
                api_key: str = None) -> Optional[str]:
        """
        Phan tich prices_report qua Gemini.
        Tra text phan tich hoac None (loi API / khong du lieu / thieu key).
        """
        if api_key is None:
            api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            self.logger.warning("SKIP: thieu GEMINI_API_KEY (env)")
            return None

        prompt = build_prompt(prices_report)
        if not prompt:
            self.logger.warning("SKIP: khong co du lieu gia de phan tich")
            return None

        for model in [self.model, FALLBACK_MODEL]:
            if model == self.model:
                pass
            elif self.model == FALLBACK_MODEL:
                break  # da thu fallback roi
            try:
                url = GEMINI_URL.format(model=model)
                payload = {
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {
                        "temperature": 0.3,
                        "maxOutputTokens": 800,
                    },
                }
                resp = requests.post(
                    url, params={"key": api_key}, json=payload,
                    timeout=self.timeout,
                    headers={"Content-Type": "application/json"},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    text = (data.get("candidates") or [{}])[0] \
                        .get("content", {}).get("parts", [{}])[0].get("text", "")
                    if text:
                        self.logger.info(f"Gemini {model} phan tich OK ({len(text)} chars)")
                        return text
                    self.logger.warning(f"Gemini {model}: response rong")
                else:
                    self.logger.warning(
                        f"Gemini {model} -> {resp.status_code}: {resp.text[:200]}"
                    )
                    # 404 model -> thu fallback
                    if resp.status_code == 404:
                        continue
                    return None
            except requests.RequestException as e:
                self.logger.warning(f"Gemini {model} loi: {e}")
                if model == FALLBACK_MODEL:
                    return None
        return None


def run_ai_analysis(logger: logging.Logger = None) -> Optional[str]:
    """Doc prices.json + goi Gemini. Tra text hoac None."""
    if logger is None:
        logger = logging.getLogger("stock_scanner")

    base_dir = Path(__file__).parent.parent.parent
    prices_path = base_dir / "output" / "real_data" / "prices.json"
    if not prices_path.exists():
        logger.warning("Khong co output/real_data/prices.json - bo qua AI phan tich")
        return None
    try:
        with open(prices_path, "r", encoding="utf-8") as f:
            prices_report = json.load(f)
    except Exception as e:
        logger.warning(f"Loi doc prices.json: {e}")
        return None

    analyst = AiAnalyst(logger=logger)
    text = analyst.analyze(prices_report)
    if text:
        # Luu ket qua
        out_path = base_dir / "output" / "real_data" / "ai_analysis.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump({
                "generated_at": datetime.now().isoformat(),
                "model": analyst.model,
                "analysis": text,
            }, f, indent=2, ensure_ascii=False)
        print(f"\n  AI phan tich OK ({len(text)} chars)")
        return text
    logger.warning("Khong co ket qua AI phan tich")
    return None
