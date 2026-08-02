"""
Telegram Report Sender - Gui bao cao pipeline qua Telegram bot.
Task: Gui tom tat tieng Viet (~1500 ky tu) sau khi pipeline chay xong.

Security:
- Token bot la SECRET - chi doc tu env var TELEGRAM_BOT_TOKEN (hoac settings).
- KHONG commit token vao repo.
- CI dung GitHub secrets, local dung env var.
"""
import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

import requests

try:
    from ..utils.config_loader import load_settings
except ImportError:
    from utils.config_loader import load_settings


TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"
MAX_TEXT_LENGTH = 1500
# Gioi han ky tu HTML an toan
_HTML_CHARS = str.maketrans({"<": "&lt;", ">": "&gt;", "&": "&amp;"})


def _read_json(path: Path) -> Optional[Any]:
    """Doc JSON file, tra None neu thieu/loi."""
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _count_capabilities(capability_report: Dict) -> Dict[str, int]:
    """Dem so capability supported/unsupported/unknown."""
    counts = {"supported": 0, "unsupported": 0, "unknown": 0}
    if not isinstance(capability_report, dict):
        return counts
    for src_key, caps in capability_report.items():
        if src_key == "generated_at" or not isinstance(caps, dict):
            continue
        for cap_name, cap_data in caps.items():
            if not isinstance(cap_data, dict):
                continue
            status = cap_data.get("status", "unknown")
            if status in counts:
                counts[status] += 1
    return counts


def _count_quality(quality_report: Dict) -> Dict[str, int]:
    """Dem quality pass/fail."""
    counts = {"pass": 0, "fail": 0}
    if not isinstance(quality_report, dict):
        return counts
    for src_key, caps in quality_report.items():
        if src_key == "generated_at" or not isinstance(caps, dict):
            continue
        for cap_name, cap_data in caps.items():
            if not isinstance(cap_data, dict):
                continue
            quality = cap_data.get("quality")
            if quality in counts:
                counts[quality] += 1
    return counts


def _count_endpoints(discovery_report: Dict) -> int:
    """Dem so endpoint phat hien (api_tests + cac endpoint khac)."""
    total = 0
    if not isinstance(discovery_report, dict):
        return 0
    for src_key, src_data in discovery_report.items():
        if src_key == "generated_at" or not isinstance(src_data, dict):
            continue
        for ep_name, ep_value in src_data.items():
            if ep_name == "api_tests" and isinstance(ep_value, list):
                total += len(ep_value)
            elif isinstance(ep_value, dict):
                total += 1
    return total


def build_summary(base_dir: str = None, config: Dict = None) -> str:
    """
    Tao text tom tat tieng Viet tu final_report + endpoint_profiles + quality_report.
    Tra ve text (~1500 ky tu). Khong goi HTTP.
    """
    if base_dir is None:
        base_dir = str(Path(__file__).parent.parent.parent)
    output_dir = Path(base_dir) / "output"

    final = _read_json(output_dir / "final_report.json") or {}
    capability = _read_json(output_dir / "capability_report.json") or {}
    discovery = _read_json(output_dir / "discovery_report.json") or {}
    profiles = _read_json(output_dir / "endpoint_profiles.json") or {}
    quality = _read_json(output_dir / "quality_report.json") or {}

    # Ngay gio
    generated_at = final.get("generated_at") or quality.get("generated_at") or datetime.now().isoformat()
    try:
        dt = datetime.fromisoformat(generated_at)
        time_str = dt.strftime("%d/%m/%Y %H:%M")
    except (ValueError, TypeError):
        time_str = str(generated_at)[:16]

    # So nguon
    connectivity = final.get("connectivity") or {}
    total_sources = connectivity.get("total_sources") if isinstance(connectivity, dict) else None
    if total_sources is None:
        # Dem tu capability_report
        total_sources = sum(1 for k in (capability or {}) if k != "generated_at")

    # Endpoint phat hien (discovery_report truc tiep)
    endpoint_count = _count_endpoints(discovery)

    # Capability
    cap_counts = _count_capabilities(capability)

    # Endpoint profiles
    profile_count = 0
    if isinstance(profiles, dict):
        for src_key, src_data in (profiles.get("sources") or {}).items():
            profile_count += len((src_data or {}).get("profiles") or [])

    # Quality
    quality_counts = _count_quality(quality)

    # Pipeline status
    pipeline = final.get("pipeline") or {}
    steps = (pipeline.get("steps") or {}) if isinstance(pipeline, dict) else {}
    failed_steps = [name for name, status in steps.items() if status != "ok"]

    lines = [
        "📊 <b>Stock Scanner - Bao cao</b>",
        f"🕐 Thoi gian: {time_str}",
        "",
        f"🌐 Nguon: {total_sources or 0}",
        f"🔍 Endpoint phat hien: {endpoint_count}",
        f"✅ Capability supported: {cap_counts['supported']}",
        f"❌ Capability unsupported: {cap_counts['unsupported']}",
        f"❓ Capability unknown: {cap_counts['unknown']}",
        f"🧩 Endpoint profiles: {profile_count}",
        f"✅ Quality pass: {quality_counts['pass']}",
        f"❌ Quality fail: {quality_counts['fail']}",
    ]

    if failed_steps:
        lines.append("")
        lines.append(f"⚠️ <b>LOI pipeline:</b> {', '.join(failed_steps)}")
    elif steps:
        lines.append("")
        lines.append("✅ Pipeline hoan tat, khong loi")

    text = "\n".join(lines)
    # Cat an toan neu vuot gioi han
    if len(text) > MAX_TEXT_LENGTH:
        text = text[: MAX_TEXT_LENGTH - 3] + "..."
    return text


def get_telegram_config(config: Dict = None) -> Dict[str, Any]:
    """
    Lay cau hinh telegram: token/chat_id tu env var (uu tien) hoac settings.
    Tra ve {"enabled", "token", "chat_id"}. Khong bao gio tra token rong.
    """
    result = {"enabled": False, "token": None, "chat_id": None}

    if config is None:
        try:
            settings = load_settings()
            config = settings.get("telegram", {})
        except Exception:
            config = {}
    config = config or {}

    # Env var uu tien (CI: GitHub secrets)
    token = os.environ.get("TELEGRAM_BOT_TOKEN") or config.get("token")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID") or config.get("chat_id")

    if token and chat_id:
        result["enabled"] = True
        result["token"] = token
        result["chat_id"] = chat_id
    return result


def send_telegram(text: str, token: str = None, chat_id: str = None,
                  logger: logging.Logger = None, timeout: int = 15,
                  retries: int = 2) -> bool:
    """
    Gui text qua Telegram bot API (POST).
    Tra ve True neu gui thanh cong, False neu that bai.
    """
    if logger is None:
        logger = logging.getLogger("telegram_sender")

    if token is None:
        token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if chat_id is None:
        chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        logger.warning("SKIP: thieu TELEGRAM_BOT_TOKEN hoac TELEGRAM_CHAT_ID (env/settings)")
        print("⚠️ SKIP: thieu Telegram credentials (TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID)")
        return False

    url = TELEGRAM_API.format(token=token)
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
    }

    for attempt in range(retries + 1):
        try:
            response = requests.post(url, data=payload, timeout=timeout)
            if response.status_code == 200:
                logger.info("Da gui bao cao Telegram thanh cong")
                return True
            logger.warning(
                f"Telegram API tra ve {response.status_code} (lan {attempt + 1}): "
                f"{response.text[:200]}"
            )
        except requests.RequestException as e:
            logger.warning(f"Loi gui Telegram (lan {attempt + 1}): {e}")
        if attempt < retries:
            time.sleep(1.0 * (attempt + 1))
    return False
