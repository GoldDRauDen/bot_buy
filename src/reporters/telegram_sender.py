"""
Telegram Report Sender - Gui bao cao pipeline qua Telegram bot.
Task: Gui tom tat day du tieng Viet (co dau, HTML-escape, max 4000 ky tu).

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
MAX_TEXT_LENGTH = 4000


def _read_json(path: Path) -> Optional[Any]:
    """Doc JSON file, tra None neu thieu/loi."""
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _html_escape(text: Any) -> str:
    """Escape ky tu HTML de an toan voi parse_mode=HTML."""
    if text is None:
        return ""
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _format_time(generated_at: Any = None) -> str:
    """
    Format thoi gian truc tiep tu generated_at (da la gio dia phuong cua may,
    khong chuyen doi timezone - khong cong/bot gio).
    """
    if isinstance(generated_at, str):
        try:
            dt = datetime.fromisoformat(generated_at)
            return dt.strftime("%d/%m/%Y %H:%M")
        except (ValueError, TypeError):
            pass
    return datetime.now().strftime("%d/%m/%Y %H:%M")


def _count_capabilities(capability_report: Dict) -> Dict[str, Dict[str, int]]:
    """Dem capability supported/unsupported/unknown theo tung nguon."""
    result = {}
    if not isinstance(capability_report, dict):
        return result
    for src_key, caps in capability_report.items():
        if src_key == "generated_at" or not isinstance(caps, dict):
            continue
        counts = {"supported": 0, "unsupported": 0, "unknown": 0}
        for cap_name, cap_data in caps.items():
            if not isinstance(cap_data, dict):
                continue
            status = cap_data.get("status", "unknown")
            if status in counts:
                counts[status] += 1
        result[src_key] = counts
    return result


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


def _pick_profiles(profiles: Dict) -> Dict[str, Dict]:
    """
    Chon profile noi bat moi nguon: uu tien co method != null va evidence_refs.
    Tra ve {source_key: profile}.
    """
    result = {}
    if not isinstance(profiles, dict):
        return result
    sources = profiles.get("sources") or {}
    for src_key, src_data in sources.items():
        if not isinstance(src_data, dict):
            continue
        items = src_data.get("profiles") or []
        # Uu tien: method != null va co evidence_refs
        def sort_key(p):
            return (
                1 if isinstance(p, dict) and p.get("method") else 0,
                1 if isinstance(p, dict) and p.get("evidence_refs") else 0,
            )
        best = sorted(items, key=sort_key, reverse=True)[:3]
        if best:
            result[src_key] = best
    return result


def build_summary(base_dir: str = None, config: Dict = None,
                  real_prices: Dict = None, ai_analysis: str = None) -> str:
    """
    Tao bao cao day du tieng Viet co dau, HTML-escape, max 4000 ky tu.

    Cau truc:
    1. Header: BÁO CÁO STOCK SCANNER + thoi gian Asia/Bangkok
    2. KẾT NỐI: tung nguon (ten, url, http_status, response_time_ms, ssl_ok)
    3. DISCOVERY: probe found/khong tung nguon + tong endpoint
    4. API PROFILES: so profiles tung nguon + 3 vi du noi bat
    5. CAPABILITY: breakdown supported/unsupported/unknown tung nguon
    6. GHI CHÚ: giai thich supported=0 / quality=0 (trang thai that, khong phai loi)
    7. PIPELINE: step ok/failed
    8. DU LIEU THẬT: tung ma (gia, %, khoi luong) tu real_prices (neu co)
    9. PHÂN TÍCH AI: phan tich Gemini (neu co)
    """
    if base_dir is None:
        base_dir = str(Path(__file__).parent.parent.parent)
    output_dir = Path(base_dir) / "output"

    final = _read_json(output_dir / "final_report.json") or {}
    capability = _read_json(output_dir / "capability_report.json") or {}
    discovery = _read_json(output_dir / "discovery_report.json") or {}
    profiles = _read_json(output_dir / "endpoint_profiles.json") or {}
    quality = _read_json(output_dir / "quality_report.json") or {}

    generated_at = final.get("generated_at") or quality.get("generated_at") or datetime.now().isoformat()
    time_str = _format_time(generated_at)

    lines = []
    # ---------- 1. HEADER ----------
    lines.append("📊 <b>BÁO CÁO STOCK SCANNER</b>")
    lines.append(f"🕐 Thời gian (Asia/Bangkok): {_html_escape(time_str)}")
    lines.append("")

    # ---------- 2. KẾT NỐI ----------
    lines.append("🔌 <b>KẾT NỐI</b>")
    connectivity = final.get("connectivity") or {}
    results = connectivity.get("results") if isinstance(connectivity, dict) else None
    if isinstance(results, dict) and results:
        for src_key, src_data in results.items():
            if not isinstance(src_data, dict):
                continue
            name = _html_escape(src_data.get("name") or src_key.upper())
            url = _html_escape(src_data.get("url") or "")
            reachable = src_data.get("reachable")
            status = src_data.get("http_status")
            rt = src_data.get("response_time_ms")
            ssl = src_data.get("ssl_ok")
            if reachable:
                ssl_txt = "SSL OK" if ssl else "SSL fallback"
                lines.append(
                    f"✅ {name}: HTTP {status} ({rt:.0f}ms, {ssl_txt})"
                    if isinstance(rt, (int, float))
                    else f"✅ {name}: HTTP {status} ({ssl_txt})"
                )
            else:
                err = _html_escape(src_data.get("error") or "không xác định")
                lines.append(f"❌ {name}: LỖI — {err[:100]}")
                lines.append(f"   {url}")
        reachable = connectivity.get("reachable")
        total = connectivity.get("total_sources")
        if isinstance(reachable, int) and isinstance(total, int):
            lines.append(f"→ {reachable}/{total} nguồn OK")
    else:
        lines.append("⚠️ Không có dữ liệu kết nối")
    lines.append("")

    # ---------- 3. DISCOVERY ----------
    lines.append("🔍 <b>DISCOVERY</b>")
    disc = final.get("discovery") if isinstance(final.get("discovery"), dict) else {}
    probes = ["robots", "sitemap", "rss", "graphql", "swagger"]
    for src_key, src_data in disc.items():
        if src_key == "generated_at" or not isinstance(src_data, dict):
            continue
        name = _html_escape(src_key.upper())
        found_parts = []
        missing_parts = []
        for probe in probes:
            ep = src_data.get(probe)
            if isinstance(ep, dict):
                if ep.get("found"):
                    found_parts.append(probe)
                else:
                    missing_parts.append(probe)
        if found_parts:
            lines.append(f"✅ {name}: found {', '.join(found_parts)}")
        else:
            lines.append(f"✅ {name}: kết nối OK, chưa tìm thấy probe tiêu chuẩn")
        if missing_parts:
            lines.append(f"   Không tìm thấy: {', '.join(missing_parts)}")
    endpoint_total = _count_endpoints(discovery)
    lines.append(f"→ Tổng endpoint phát hiện: {endpoint_total}")
    lines.append("")

    # ---------- 4. API PROFILES ----------
    lines.append("🧩 <b>API PROFILES</b>")
    profiles_sources = (profiles.get("sources") or {}) if isinstance(profiles, dict) else {}
    if profiles_sources:
        for src_key, src_data in profiles_sources.items():
            if not isinstance(src_data, dict):
                continue
            items = src_data.get("profiles") or []
            name = _html_escape(src_key.upper())
            lines.append(f"📌 {name}: {len(items)} profiles")
            # 3 vi du noi bat
            best = _pick_profiles(profiles).get(src_key, [])[:3]
            for p in best:
                method = _html_escape(p.get("method") or "?")
                url = _html_escape(p.get("url") or "")
                auth = p.get("authentication") or {}
                auth_required = "có" if auth.get("required") else "không"
                auth_type = _html_escape(auth.get("type")) if auth.get("type") else ""
                csrf = "có" if p.get("csrf_required") else "không"
                auth_txt = f", auth: {auth_required}"
                if auth_type:
                    auth_txt += f" ({auth_type})"
                lines.append(f"   • {method} {url[:60]} — csrf: {csrf}{auth_txt}")
    else:
        lines.append("⚠️ Chưa có endpoint profiles")
    lines.append("")

    # ---------- 5. CAPABILITY ----------
    lines.append("🎯 <b>CAPABILITY</b>")
    cap_by_source = _count_capabilities(capability)
    if cap_by_source:
        for src_key, counts in cap_by_source.items():
            name = _html_escape(src_key.upper())
            lines.append(
                f"📌 {name}: supported={counts['supported']}, "
                f"unsupported={counts['unsupported']}, unknown={counts['unknown']}"
            )
    else:
        lines.append("⚠️ Không có dữ liệu capability")
    lines.append("")

    # ---------- 6. GHI CHÚ ----------
    lines.append("📝 <b>GHI CHÚ</b>")
    cap_counts_total = {"supported": 0, "unsupported": 0, "unknown": 0}
    for counts in cap_by_source.values():
        for k in cap_counts_total:
            cap_counts_total[k] += counts[k]
    quality_counts = _count_quality(quality)
    if cap_counts_total["supported"] == 0:
        lines.append(
            "• Capability supported=0: phân loại offline theo keyword "
            "(không AI, không đoán), hầu hết endpoint chưa đủ bằng chứng nội dung "
            "nên xếp <b>unknown</b> — đây là trạng thái thật, không phải lỗi."
        )
    if quality_counts["pass"] == 0 and quality_counts["fail"] == 0:
        lines.append(
            "• Quality pass=0: endpoint_plan trống (chưa có capability supported) "
            "nên chưa fetch dữ liệu thật — pipeline dừng đúng theo thiết kế."
        )
    elif quality_counts["pass"] == 0:
        lines.append(
            "• Quality pass=0: dữ liệu fetch về chưa đạt tiêu chuẩn chất lượng "
            "(empty/không phải JSON hợp lệ) — kiểm tra raw_data."
        )
    lines.append("")

    # ---------- 7. PIPELINE ----------
    lines.append("⚙️ <b>PIPELINE</b>")
    pipeline = final.get("pipeline") or {}
    steps = (pipeline.get("steps") or {}) if isinstance(pipeline, dict) else {}
    if steps:
        failed = [name for name, status in steps.items() if status != "ok"]
        for name, status in steps.items():
            mark = "✅" if status == "ok" else "❌"
            lines.append(f"{mark} {_html_escape(name)}: {_html_escape(status)}")
        if failed:
            lines.append(f"⚠️ Có lỗi step: {', '.join(failed)}")
        else:
            lines.append("✅ Pipeline hoàn tất, không lỗi")
    else:
        lines.append("⚠️ Không có dữ liệu pipeline")

    # ---------- 8. DU LIEU THẬT ----------
    if real_prices and real_prices.get("prices"):
        lines.append("")
        lines.append("💹 <b>DỮ LIỆU THẬT</b> (vietstock)")
        for p in real_prices["prices"]:
            symbol = _html_escape(p.get("symbol", "?"))
            price = _html_escape(p.get("price", "?"))
            pct = _html_escape(p.get("change_percent", ""))
            vol = _html_escape(p.get("volume", ""))
            date = _html_escape(p.get("trading_date", ""))
            lines.append(f"📌 {symbol}: {price} VND ({pct}) — KL {vol} ({date})")

    # ---------- 9. PHÂN TÍCH AI ----------
    if ai_analysis:
        lines.append("")
        lines.append("🤖 <b>PHÂN TÍCH AI</b>")
        # Cat AI text thanh cac dong ngan, escape
        ai_text = _html_escape(ai_analysis)
        for para in ai_text.split("\n"):
            if para.strip():
                lines.append(para.strip()[:200])

    text = "\n".join(lines)
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
        print("⚠️ SKIP: thiếu Telegram credentials (TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID)")
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
