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
# Model da chay thanh cong thuc te o du an khac
FALLBACK_MODEL = "gemini-flash-latest"


def build_prompt(prices_report: Dict[str, Any],
                 extra_instruction: str = "") -> str:
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
        "Yêu cầu: Hãy viết phân tích TỐI THIỂU 5 câu hoàn chỉnh, theo đúng 3 phần: "
        "[1] Tổng quan phiên giao dịch - 2 câu, "
        "[2] Diễn biến nổi bật và điểm đáng chú ý - 2 câu, "
        "[3] Cảnh báo rủi ro - 1 câu. "
        "KHÔNG được trả lời ngắn hơn 5 câu. "
        "Chỉ dùng số liệu được cung cấp, không thêm số liệu khác, không bịa."
    )
    if extra_instruction:
        lines.append("")
        lines.append(extra_instruction)
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

        models_to_try = [self.model]
        if FALLBACK_MODEL != self.model:
            models_to_try.append(FALLBACK_MODEL)

        for model in models_to_try:
            try:
                url = GEMINI_URL.format(model=model)
                payload = {
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {
                        "temperature": 0.4,
                        "maxOutputTokens": 1200,
                        "candidateCount": 1,
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
            except requests.RequestException as e:
                self.logger.warning(f"Gemini {model} loi: {e}")
            # Loi (404/429/5xx/timeout/rong) -> thu model tiep theo
        return None

    def analyze_with_prompt(self, extra_instruction: str,
                            prices_report: Dict[str, Any],
                            api_key: str = None) -> Optional[str]:
        """
        Goi Gemini lai voi instruction bo sung (vi du: yeu cau chi tiet hon).
        Dung build_prompt voi extra_instruction. Tra None neu loi.
        """
        if api_key is None:
            api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            return None
        prompt = build_prompt(prices_report, extra_instruction=extra_instruction)
        if not prompt:
            return None

        models_to_try = [self.model]
        if FALLBACK_MODEL != self.model:
            models_to_try.append(FALLBACK_MODEL)

        for model in models_to_try:
            try:
                url = GEMINI_URL.format(model=model)
                payload = {
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {
                        "temperature": 0.4,
                        "maxOutputTokens": 1200,
                        "candidateCount": 1,
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
                        self.logger.info(
                            f"Gemini {model} (retry) phan tich OK ({len(text)} chars)"
                        )
                        return text
                    self.logger.warning(f"Gemini {model} (retry): response rong")
                else:
                    self.logger.warning(
                        f"Gemini {model} (retry) -> {resp.status_code}: {resp.text[:200]}"
                    )
            except requests.RequestException as e:
                self.logger.warning(f"Gemini {model} (retry) loi: {e}")
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
