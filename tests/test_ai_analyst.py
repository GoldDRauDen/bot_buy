"""
Unit tests cho AI Analyst (PHA 2).
Offline tests (mock requests). Khong network, khong key that.
"""
import sys
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from analyst.ai_analyst import AiAnalyst, build_prompt


SAMPLE_PRICES = {
    "prices": [
        {"symbol": "ACB", "price": "21,900", "change_percent": "(-2.01%)",
         "volume": "15,165,000", "open": "22,600", "high": "22,600",
         "low": "21,800", "trading_date": "31/07/2026"},
        {"symbol": "FPT", "price": "67,100", "change_percent": "(+0.75%)",
         "volume": "6,253,600", "open": "66,500", "high": "67,500",
         "low": "66,200", "trading_date": "31/07/2026"},
    ]
}


class TestBuildPrompt:
    """Test build_prompt."""

    def test_prompt_contains_data(self):
        prompt = build_prompt(SAMPLE_PRICES)
        assert "ACB" in prompt
        assert "21,900" in prompt
        assert "(-2.01%)" in prompt
        assert "FPT" in prompt
        assert "vietstock" in prompt

    def test_prompt_empty(self):
        assert build_prompt({"prices": []}) == ""

    def test_prompt_no_speculation(self):
        """Prompt yeu cau chi dung so lieu cung cap."""
        prompt = build_prompt(SAMPLE_PRICES)
        assert "KHÔNG thêm số liệu khác" in prompt or "KHONG them so lieu khac" in prompt
        assert "Cảnh báo rủi ro" in prompt


class TestAiAnalyst:
    """Test analyze (mock requests)."""

    def test_success(self):
        analyst = AiAnalyst(config={"model": "gemini-2.0-flash"})
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": "Thị trường tăng nhẹ..."}]}}]
        }
        with patch("analyst.ai_analyst.requests.post", return_value=mock_response) as mock_post:
            result = analyst.analyze(SAMPLE_PRICES, api_key="test-key")

        assert result == "Thị trường tăng nhẹ..."
        # Dung URL + key
        url = mock_post.call_args[0][0]
        assert "generateContent" in url
        assert mock_post.call_args.kwargs["params"]["key"] == "test-key"
        # Prompt trong payload
        payload = mock_post.call_args.kwargs["json"]
        assert "ACB" in payload["contents"][0]["parts"][0]["text"]

    def test_missing_key(self):
        analyst = AiAnalyst(config={})
        with patch.dict("os.environ", {}, clear=True):
            result = analyst.analyze(SAMPLE_PRICES)
        assert result is None

    def test_no_data(self):
        analyst = AiAnalyst(config={})
        result = analyst.analyze({"prices": []}, api_key="k")
        assert result is None

    def test_model_404_fallback(self):
        """Model 404 -> thu fallback gemini-flash-latest."""
        analyst = AiAnalyst(config={"model": "gemini-2.0-flash"})
        mock_404 = MagicMock(status_code=404, text="model not found")
        mock_ok = MagicMock()
        mock_ok.status_code = 200
        mock_ok.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": "OK fallback"}]}}]
        }
        with patch("analyst.ai_analyst.requests.post",
                   side_effect=[mock_404, mock_ok]) as mock_post:
            result = analyst.analyze(SAMPLE_PRICES, api_key="k")

        assert result == "OK fallback"
        assert mock_post.call_count == 2
        # Fallback model dung
        url2 = mock_post.call_args_list[1][0][0]
        assert "gemini-flash-latest" in url2

    def test_model_429_fallback(self):
        """429 (rate limit) -> thu fallback gemini-flash-latest."""
        analyst = AiAnalyst(config={"model": "gemini-2.0-flash"})
        mock_429 = MagicMock(status_code=429, text="rate limited")
        mock_ok = MagicMock()
        mock_ok.status_code = 200
        mock_ok.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": "OK sau 429"}]}}]
        }
        with patch("analyst.ai_analyst.requests.post",
                   side_effect=[mock_429, mock_ok]) as mock_post:
            result = analyst.analyze(SAMPLE_PRICES, api_key="k")

        assert result == "OK sau 429"
        assert mock_post.call_count == 2
        assert "gemini-flash-latest" in mock_post.call_args_list[1][0][0]

    def test_5xx_fallback(self):
        """500 -> thu fallback."""
        analyst = AiAnalyst(config={"model": "gemini-2.0-flash"})
        mock_500 = MagicMock(status_code=500, text="server error")
        mock_ok = MagicMock()
        mock_ok.status_code = 200
        mock_ok.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": "OK sau 500"}]}}]
        }
        with patch("analyst.ai_analyst.requests.post",
                   side_effect=[mock_500, mock_ok]) as mock_post:
            result = analyst.analyze(SAMPLE_PRICES, api_key="k")
        assert result == "OK sau 500"
        assert mock_post.call_count == 2

    def test_timeout_fallback(self):
        """Timeout -> thu fallback."""
        import requests
        analyst = AiAnalyst(config={"model": "gemini-2.0-flash"})
        mock_ok = MagicMock()
        mock_ok.status_code = 200
        mock_ok.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": "OK sau timeout"}]}}]
        }
        with patch("analyst.ai_analyst.requests.post",
                   side_effect=[requests.Timeout("slow"), mock_ok]) as mock_post:
            result = analyst.analyze(SAMPLE_PRICES, api_key="k")
        assert result == "OK sau timeout"
        assert mock_post.call_count == 2

    def test_empty_response_fallback(self):
        """Response rong -> thu fallback."""
        analyst = AiAnalyst(config={"model": "gemini-2.0-flash"})
        mock_empty = MagicMock()
        mock_empty.status_code = 200
        mock_empty.json.return_value = {"candidates": []}
        mock_ok = MagicMock()
        mock_ok.status_code = 200
        mock_ok.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": "OK sau rong"}]}}]
        }
        with patch("analyst.ai_analyst.requests.post",
                   side_effect=[mock_empty, mock_ok]) as mock_post:
            result = analyst.analyze(SAMPLE_PRICES, api_key="k")
        assert result == "OK sau rong"
        assert mock_post.call_count == 2

    def test_both_fail_returns_none(self):
        """Ca 2 model deu that bai -> None."""
        analyst = AiAnalyst(config={"model": "gemini-2.0-flash"})
        mock_429 = MagicMock(status_code=429, text="rate limited")
        mock_500 = MagicMock(status_code=500, text="server error")
        with patch("analyst.ai_analyst.requests.post",
                   side_effect=[mock_429, mock_500]) as mock_post:
            result = analyst.analyze(SAMPLE_PRICES, api_key="k")
        assert result is None
        assert mock_post.call_count == 2

    def test_http_error_no_fallback(self):
        """Loi 500 -> thu fallback, ca 2 loi -> None."""
        analyst = AiAnalyst(config={"model": "gemini-2.0-flash"})
        mock_500 = MagicMock(status_code=500, text="server error")
        mock_502 = MagicMock(status_code=502, text="bad gateway")
        with patch("analyst.ai_analyst.requests.post",
                   side_effect=[mock_500, mock_502]) as mock_post:
            result = analyst.analyze(SAMPLE_PRICES, api_key="k")
        assert result is None
        assert mock_post.call_count == 2

    def test_empty_response(self):
        """Response rong ca 2 model -> None."""
        analyst = AiAnalyst(config={"model": "gemini-2.0-flash"})
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"candidates": []}
        with patch("analyst.ai_analyst.requests.post", return_value=mock_response):
            result = analyst.analyze(SAMPLE_PRICES, api_key="k")
        assert result is None

    def test_same_model_no_duplicate(self):
        """settings.model = gemini-flash-latest -> chi thu 1 lan."""
        analyst = AiAnalyst(config={"model": "gemini-flash-latest"})
        mock_ok = MagicMock()
        mock_ok.status_code = 200
        mock_ok.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": "OK"}]}}]
        }
        with patch("analyst.ai_analyst.requests.post", return_value=mock_ok) as mock_post:
            result = analyst.analyze(SAMPLE_PRICES, api_key="k")
        assert result == "OK"
        assert mock_post.call_count == 1
        assert "gemini-flash-latest" in mock_post.call_args[0][0]
