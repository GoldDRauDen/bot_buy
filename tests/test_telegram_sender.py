"""
Unit tests cho Telegram report sender (format day du).
Offline tests: build_summary voi report mau, send_telegram monkeypatch requests,
thieu credential -> skip. Khong co network.
"""
import sys
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from reporters.telegram_sender import (
    build_summary, send_telegram, get_telegram_config,
)


class TestBuildSummary:
    """Test build_summary format day du."""

    def _write_reports(self, tmp_path, final=None, quality=None, profiles=None,
                       capability=None, discovery=None):
        out = tmp_path / "output"
        out.mkdir(parents=True, exist_ok=True)

        default_final = {
            "generated_at": "2026-08-02T10:00:00.000000",
            "pipeline": {
                "steps": {
                    "connectivity": "ok", "discovery": "ok", "capability": "ok",
                    "index": "ok", "endpoint_plan": "ok", "quality": "ok",
                }
            },
            "connectivity": {
                "total_sources": 2, "reachable": 2, "unreachable": 0,
                "results": {
                    "hose": {"name": "HOSE", "url": "https://www.hsx.vn/",
                             "reachable": True, "http_status": 200,
                             "response_time_ms": 266.98, "ssl_ok": True,
                             "error": None},
                    "hnx": {"name": "HNX", "url": "https://www.hnx.vn/",
                            "reachable": True, "http_status": 200,
                            "response_time_ms": 360.12, "ssl_ok": False,
                            "error": None},
                },
            },
            "discovery": {
                "hose": {
                    "robots": {"found": True}, "sitemap": {"found": False},
                    "rss": {"found": False}, "graphql": {"found": False},
                    "swagger": {"found": False},
                },
                "hnx": {
                    "robots": {"found": True}, "sitemap": {"found": False},
                    "rss": {"found": True}, "graphql": {"found": False},
                    "swagger": {"found": False},
                },
            },
        }
        default_quality = {
            "generated_at": "2026-08-02T10:00:00.000000",
            "hose": {"stock_list": {"quality": "pass"}},
        }
        default_profiles = {
            "sources": {
                "hose": {
                    "profiles": [
                        {"method": "GET", "url": "/api/v1/stocks",
                         "authentication": {"required": True, "type": "bearer"},
                         "csrf_required": True, "evidence_refs": [{"field": "x"}]},
                        {"method": None, "url": "/api/other",
                         "authentication": {"required": False, "type": None},
                         "csrf_required": False},
                    ]
                },
                "hnx": {
                    "profiles": [
                        {"method": "POST", "url": "/Home/GetDataArticles",
                         "authentication": {"required": False, "type": None},
                         "csrf_required": False, "evidence_refs": [{"field": "y"}]},
                    ]
                },
            }
        }
        default_capability = {
            "generated_at": "2026-08-02T10:00:00.000000",
            "hose": {
                "stock_list": {"status": "supported"},
                "current_price": {"status": "unsupported"},
                "historical_price": {"status": "unknown"},
            },
            "hnx": {
                "stock_list": {"status": "unknown"},
                "current_price": {"status": "unknown"},
            },
        }
        default_discovery = {
            "hose": {"api_tests": [{"url": "/a"}, {"url": "/b"}], "robots": {"url": "/robots"}},
            "hnx": {"api_tests": [{"url": "/c"}]},
        }

        for name, data in [
            ("final_report.json", final if final is not None else default_final),
            ("quality_report.json", quality if quality is not None else default_quality),
            ("endpoint_profiles.json", profiles if profiles is not None else default_profiles),
            ("capability_report.json", capability if capability is not None else default_capability),
            ("discovery_report.json", discovery if discovery is not None else default_discovery),
        ]:
            (out / name).write_text(json.dumps(data), encoding="utf-8")

    def test_header(self, tmp_path):
        """Header + thoi gian truc tiep (khong chuyen doi timezone)."""
        self._write_reports(tmp_path)
        text = build_summary(str(tmp_path))
        assert "BÁO CÁO STOCK SCANNER" in text
        assert "Asia/Bangkok" in text
        # generated_at 10:00 -> hien thi truc tiep 10:00 (khong cong +7)
        assert "10:00" in text
        assert "17:00" not in text

    def test_connectivity_section(self, tmp_path):
        """KET NOI: tung nguon + ssl + thoi gian."""
        self._write_reports(tmp_path)
        text = build_summary(str(tmp_path))
        assert "KẾT NỐI" in text
        assert "HOSE" in text
        assert "HNX" in text
        assert "SSL OK" in text
        assert "SSL fallback" in text
        assert "2/2 nguồn OK" in text

    def test_connectivity_error_source(self, tmp_path):
        """Nguon loi -> ghi ro loi."""
        final = {
            "generated_at": "2026-08-02T10:00:00.000000",
            "pipeline": {"steps": {}},
            "connectivity": {
                "total_sources": 1, "reachable": 0, "unreachable": 1,
                "results": {
                    "hose": {"name": "HOSE", "url": "https://www.hsx.vn/",
                             "reachable": False, "http_status": None,
                             "response_time_ms": None, "ssl_ok": False,
                             "error": "Connection timed out"},
                },
            },
            "discovery": {},
        }
        self._write_reports(tmp_path, final=final)
        text = build_summary(str(tmp_path))
        assert "LỖI" in text
        assert "Connection timed out" in text
        assert "0/1 nguồn OK" in text

    def test_discovery_section(self, tmp_path):
        """DISCOVERY: probe found + tong endpoint."""
        self._write_reports(tmp_path)
        text = build_summary(str(tmp_path))
        assert "DISCOVERY" in text
        assert "found robots" in text
        assert "Tổng endpoint phát hiện: 4" in text  # 2 api_tests + 1 robots + 1 api_test

    def test_profiles_section(self, tmp_path):
        """API PROFILES: so profiles + vi du noi bat (u tien method)."""
        self._write_reports(tmp_path)
        text = build_summary(str(tmp_path))
        assert "API PROFILES" in text
        assert "2 profiles" in text
        assert "1 profiles" in text
        # Vi du noi bat: GET /api/v1/stocks co method + auth bearer + csrf
        assert "GET /api/v1/stocks" in text
        assert "auth: có (bearer)" in text
        assert "csrf: có" in text

    def test_capability_section(self, tmp_path):
        """CAPABILITY: breakdown theo nguon."""
        self._write_reports(tmp_path)
        text = build_summary(str(tmp_path))
        assert "CAPABILITY" in text
        assert "hose".upper() in text or "HOSE" in text
        assert "supported=1, unsupported=1, unknown=1" in text
        assert "unknown=2" in text  # hnx

    def test_notes_section_supported_zero(self, tmp_path):
        """GHI CHU: supported=0 giai thich."""
        # Capability toan unknown -> supported=0
        capability = {
            "hose": {"stock_list": {"status": "unknown"}},
        }
        self._write_reports(tmp_path, capability=capability)
        text = build_summary(str(tmp_path))
        assert "GHI CHÚ" in text
        assert "supported=0" in text
        assert "unknown" in text

    def test_notes_section_quality_zero(self, tmp_path):
        """GHI CHU: quality=0 giai thich."""
        quality = {"hose": {}}
        self._write_reports(tmp_path, quality=quality)
        text = build_summary(str(tmp_path))
        assert "quality" in text.lower()

    def test_pipeline_section(self, tmp_path):
        """PIPELINE: step ok/failed."""
        self._write_reports(tmp_path)
        text = build_summary(str(tmp_path))
        assert "PIPELINE" in text
        assert "connectivity: ok" in text
        assert "Pipeline hoàn tất" in text

    def test_pipeline_failure(self, tmp_path):
        """Pipeline co loi -> ghi nhan."""
        self._write_reports(tmp_path, final={
            "generated_at": "2026-08-02T10:00:00.000000",
            "pipeline": {"steps": {"connectivity": "ok", "discovery": "failed"}},
            "connectivity": {},
            "discovery": {},
        })
        text = build_summary(str(tmp_path))
        assert "discovery: failed" in text
        assert "Có lỗi step" in text

    def test_missing_files(self, tmp_path):
        """Thieu file bao cao -> van tao text khong loi."""
        out = tmp_path / "output"
        out.mkdir(parents=True)
        (out / "final_report.json").write_text(
            json.dumps({"generated_at": "2026-08-02T10:00:00"}), encoding="utf-8"
        )
        text = build_summary(str(tmp_path))
        assert isinstance(text, str)
        assert len(text) > 0

    def test_length_limit_4000(self, tmp_path):
        """Text khong vuot 4000 ky tu."""
        self._write_reports(tmp_path)
        text = build_summary(str(tmp_path))
        assert len(text) <= 4000

    def test_html_escaped(self, tmp_path):
        """Ky tu HTML duoc escape."""
        final = {
            "generated_at": "2026-08-02T10:00:00.000000",
            "pipeline": {"steps": {}},
            "connectivity": {
                "total_sources": 1, "reachable": 0, "unreachable": 1,
                "results": {
                    "hose": {"name": "HOSE", "url": "https://x.com/?a=1&b=2",
                             "reachable": False, "http_status": None,
                             "response_time_ms": None, "ssl_ok": False,
                             "error": "timeout <5s> & retry"},
                },
            },
            "discovery": {},
        }
        self._write_reports(tmp_path, final=final)
        text = build_summary(str(tmp_path))
        assert "&amp;" in text
        assert "&lt;5s&gt;" in text
        # Khong co raw HTML khong escape
        assert "<5s>" not in text


class TestGetTelegramConfig:
    """Test doc cau hinh telegram."""

    def test_from_env(self, monkeypatch):
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "secret-token")
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "12345")
        cfg = get_telegram_config({})
        assert cfg["enabled"] is True
        assert cfg["token"] == "secret-token"
        assert cfg["chat_id"] == "12345"

    def test_from_settings_config(self, monkeypatch):
        monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
        monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
        cfg = get_telegram_config({"token": "cfg-token", "chat_id": "cfg-chat"})
        assert cfg["enabled"] is True
        assert cfg["token"] == "cfg-token"

    def test_missing_credentials(self, monkeypatch):
        monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
        monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
        cfg = get_telegram_config({})
        assert cfg["enabled"] is False


class TestSendTelegram:
    """Test send_telegram (monkeypatch requests, khong network)."""

    def test_success(self, monkeypatch):
        """Gui thanh cong -> True."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "ok"
        mock_post = MagicMock(return_value=mock_response)

        with patch("reporters.telegram_sender.requests.post", mock_post):
            result = send_telegram("test", token="tok", chat_id="123")

        assert result is True
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert call_args[0][0] == "https://api.telegram.org/bottok/sendMessage"
        payload = call_args.kwargs["data"]
        assert payload["chat_id"] == "123"
        assert payload["parse_mode"] == "HTML"

    def test_retry_on_error(self, monkeypatch):
        """Loi mang -> retry -> False."""
        import requests
        mock_post = MagicMock(side_effect=requests.Timeout("timeout"))

        with patch("reporters.telegram_sender.requests.post", mock_post):
            with patch("reporters.telegram_sender.time.sleep"):
                result = send_telegram("test", token="tok", chat_id="123", retries=2)

        assert result is False
        assert mock_post.call_count == 3  # 1 + 2 retries

    def test_missing_credentials(self, monkeypatch):
        """Thieu credential -> False, khong goi network."""
        mock_post = MagicMock()
        with patch("reporters.telegram_sender.requests.post", mock_post):
            with patch.dict("os.environ", {}, clear=True):
                result = send_telegram("test")

        assert result is False
        mock_post.assert_not_called()

    def test_http_error(self, monkeypatch):
        """API tra ve non-200 -> False."""
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.text = "unauthorized"
        mock_post = MagicMock(return_value=mock_response)

        with patch("reporters.telegram_sender.requests.post", mock_post):
            with patch("reporters.telegram_sender.time.sleep"):
                result = send_telegram("test", token="tok", chat_id="123")

        assert result is False
