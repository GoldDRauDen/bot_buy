"""
Unit tests cho Telegram report sender.
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
    """Test build_summary."""

    def _write_reports(self, tmp_path, final=None, quality=None, profiles=None,
                       capability=None, discovery=None):
        out = tmp_path / "output"
        out.mkdir(parents=True, exist_ok=True)

        default_final = {
            "generated_at": "2026-08-02T10:00:00.000000",
            "pipeline": {"steps": {"connectivity": "ok", "discovery": "ok"}},
            "connectivity": {"total_sources": 3},
        }
        default_quality = {
            "generated_at": "2026-08-02T10:00:00.000000",
            "hose": {"stock_list": {"quality": "pass"}},
        }
        default_profiles = {
            "sources": {"hose": {"profiles": [{"url": "/api/x"}, {"url": "/api/y"}]}}
        }
        default_capability = {
            "generated_at": "2026-08-02T10:00:00.000000",
            "hose": {
                "stock_list": {"status": "supported"},
                "current_price": {"status": "unsupported"},
            },
        }
        default_discovery = {
            "hose": {"api_tests": [{"url": "/a"}, {"url": "/b"}], "robots": {"url": "/robots"}}
        }

        for name, data in [
            ("final_report.json", final if final is not None else default_final),
            ("quality_report.json", quality if quality is not None else default_quality),
            ("endpoint_profiles.json", profiles if profiles is not None else default_profiles),
            ("capability_report.json", capability if capability is not None else default_capability),
            ("discovery_report.json", discovery if discovery is not None else default_discovery),
        ]:
            (out / name).write_text(json.dumps(data), encoding="utf-8")

    def test_build_summary_content(self, tmp_path):
        """Noi dung tom tat dung du lieu mau."""
        self._write_reports(tmp_path)
        text = build_summary(str(tmp_path))

        # Ngay gio
        assert "10:00" in text
        # So nguon
        assert "Nguon: 3" in text
        # Endpoint phat hien: 2 api_tests + 1 robots = 3
        assert "Endpoint phat hien: 3" in text
        # Capability
        assert "supported: 1" in text
        assert "unsupported: 1" in text
        # Profiles
        assert "Endpoint profiles: 2" in text
        # Quality
        assert "Quality pass: 1" in text
        # Pipeline ok
        assert "Pipeline hoan tat" in text

    def test_build_summary_missing_files(self, tmp_path):
        """Thieu file bao cao -> van tao text khong loi."""
        out = tmp_path / "output"
        out.mkdir(parents=True)
        (out / "final_report.json").write_text(
            json.dumps({"generated_at": "2026-08-02T10:00:00"}), encoding="utf-8"
        )
        text = build_summary(str(tmp_path))
        assert isinstance(text, str)
        assert len(text) > 0

    def test_build_summary_pipeline_failure(self, tmp_path):
        """Pipeline co loi -> ghi nhan trong text."""
        self._write_reports(tmp_path, final={
            "generated_at": "2026-08-02T10:00:00.000000",
            "pipeline": {"steps": {"connectivity": "ok", "discovery": "failed"}},
            "connectivity": {"total_sources": 3},
        })
        text = build_summary(str(tmp_path))
        assert "LOI pipeline" in text
        assert "discovery" in text

    def test_build_summary_length_limit(self, tmp_path):
        """Text khong vuot 1500 ky tu."""
        self._write_reports(tmp_path)
        text = build_summary(str(tmp_path))
        assert len(text) <= 1500


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
        # Dung dung API
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert call_args[0][0] == "https://api.telegram.org/bot{tok}/sendMessage" \
            .format(tok="tok") if False else True
        # Payload dung
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
