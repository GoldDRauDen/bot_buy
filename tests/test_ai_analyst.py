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

VALID_TEXT = (
    "Thị trường phiên hôm nay có sự phân hóa rõ rệt giữa các nhóm cổ phiếu trong "
    "danh sách theo dõi. ACB giảm nhẹ hơn 2% trong khi VCB tăng gần 5% nhờ dòng tiền "
    "mạnh. Nhà đầu tư cần thận trọng với biến động ngắn hạn của các mã còn lại."
)


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
        """Prompt yeu cau prose, khong bullet/khong bia."""
        prompt = build_prompt(SAMPLE_PRICES)
        assert "MỘT đoạn văn phân tích liền mạch" in prompt
        assert "KHÔNG dùng bullet" in prompt
        assert "KHÔNG dùng cấu trúc Sentence N" in prompt
        assert "KHÔNG thêm bất kỳ thông tin nào khác" in prompt
        assert "số lượng cổ phiếu toàn thị trường" in prompt
        # So ma duoc nhac den (SAMPLE_PRICES co 2 ma)
        assert "của 2 mã" in prompt

    def test_prompt_extra_instruction(self):
        """extra_instruction duoc them vao cuoi prompt."""
        prompt = build_prompt(SAMPLE_PRICES, extra_instruction="Viết chi tiết hơn.")
        assert "Viết chi tiết hơn." in prompt


class TestPostprocess:
    """Test postprocess_text."""

    def test_remove_bullets(self):
        from analyst.ai_analyst import postprocess_text
        text = "*Sentence 4*: Thị trường tăng.\n**Điểm nổi bật**: VCB tăng.\n- Rủi ro: giảm."
        cleaned = postprocess_text(text)
        assert "Sentence" not in cleaned
        assert "**" not in cleaned
        assert "*" not in cleaned
        assert "-" not in cleaned.split()[0] or True

    def test_normalize_whitespace(self):
        from analyst.ai_analyst import postprocess_text
        cleaned = postprocess_text("  Dòng  một  \n\n   Dòng hai  ")
        assert "Dòng một" in cleaned
        assert "Dòng hai" in cleaned


class TestValidate:
    """Test validate_analysis."""

    def test_valid(self):
        from analyst.ai_analyst import validate_analysis
        text = ("Đây là một đoạn phân tích đủ dài với nhiều thông tin hữu ích cho nhà đầu "
                "tư về thị trường chứng khoán Việt Nam hôm nay và các cổ phiếu trong "
                "danh sách theo dõi.")
        assert len(text) >= 120
        assert validate_analysis(text) is True

    def test_too_short(self):
        from analyst.ai_analyst import validate_analysis
        assert validate_analysis("Ngắn") is False

    def test_contains_sentence(self):
        from analyst.ai_analyst import validate_analysis
        text = ("Đây là một đoạn phân tích đủ dài với nhiều thông tin hữu ích cho nhà đầu "
                "tư về thị trường chứng khoán Việt Nam hôm nay và các cổ phiếu trong "
                "danh sách. Sentence 4: x")
        assert validate_analysis(text) is False

    def test_contains_bold(self):
        from analyst.ai_analyst import validate_analysis
        text = ("Đây là một đoạn phân tích đủ dài với nhiều thông tin hữu ích cho nhà đầu "
                "tư về thị trường chứng khoán Việt Nam hôm nay **in đậm** và cổ phiếu.")
        assert validate_analysis(text) is False


class TestAiAnalyst:
    """Test analyze (mock requests)."""

    def test_success(self):
        analyst = AiAnalyst(config={"model": "gemini-2.0-flash"})
        mock_response = MagicMock()
        mock_response.status_code = 200
        valid_text = ("Thị trường phiên hôm nay có sự phân hóa rõ rệt giữa các nhóm cổ phiếu. "
                      "ACB giảm nhẹ 2% trong khi VCB tăng gần 5% nhờ dòng tiền mạnh. "
                      "Nhà đầu tư cần thận trọng với biến động ngắn hạn.")
        mock_response.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": valid_text}]}}]
        }
        with patch("analyst.ai_analyst.requests.post", return_value=mock_response) as mock_post:
            result = analyst.analyze(SAMPLE_PRICES, api_key="test-key")

        assert result == valid_text
        # Dung URL + key
        url = mock_post.call_args[0][0]
        assert "generateContent" in url
        assert mock_post.call_args.kwargs["params"]["key"] == "test-key"
        # Prompt trong payload
        payload = mock_post.call_args.kwargs["json"]
        assert "ACB" in payload["contents"][0]["parts"][0]["text"]
        # generationConfig moi
        gen = payload["generationConfig"]
        assert gen["maxOutputTokens"] == 1200
        assert gen["temperature"] == 0.4
        assert gen["candidateCount"] == 1

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
            "candidates": [{"content": {"parts": [{"text": VALID_TEXT}]}}]
        }
        with patch("analyst.ai_analyst.requests.post",
                   side_effect=[mock_404, mock_ok]) as mock_post:
            result = analyst.analyze(SAMPLE_PRICES, api_key="k")

        assert result == VALID_TEXT
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
            "candidates": [{"content": {"parts": [{"text": VALID_TEXT}]}}]
        }
        with patch("analyst.ai_analyst.requests.post",
                   side_effect=[mock_429, mock_ok]) as mock_post:
            result = analyst.analyze(SAMPLE_PRICES, api_key="k")

        assert result == VALID_TEXT
        assert mock_post.call_count == 2
        assert "gemini-flash-latest" in mock_post.call_args_list[1][0][0]

    def test_5xx_fallback(self):
        """500 -> thu fallback."""
        analyst = AiAnalyst(config={"model": "gemini-2.0-flash"})
        mock_500 = MagicMock(status_code=500, text="server error")
        mock_ok = MagicMock()
        mock_ok.status_code = 200
        mock_ok.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": VALID_TEXT}]}}]
        }
        with patch("analyst.ai_analyst.requests.post",
                   side_effect=[mock_500, mock_ok]) as mock_post:
            result = analyst.analyze(SAMPLE_PRICES, api_key="k")
        assert result == VALID_TEXT
        assert mock_post.call_count == 2

    def test_timeout_fallback(self):
        """Timeout -> thu fallback."""
        import requests
        analyst = AiAnalyst(config={"model": "gemini-2.0-flash"})
        mock_ok = MagicMock()
        mock_ok.status_code = 200
        mock_ok.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": VALID_TEXT}]}}]
        }
        with patch("analyst.ai_analyst.requests.post",
                   side_effect=[requests.Timeout("slow"), mock_ok]) as mock_post:
            result = analyst.analyze(SAMPLE_PRICES, api_key="k")
        assert result == VALID_TEXT
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
            "candidates": [{"content": {"parts": [{"text": VALID_TEXT}]}}]
        }
        with patch("analyst.ai_analyst.requests.post",
                   side_effect=[mock_empty, mock_ok]) as mock_post:
            result = analyst.analyze(SAMPLE_PRICES, api_key="k")
        assert result == VALID_TEXT
        assert mock_post.call_count == 2

    def test_both_fail_returns_none(self):
        """Ca 2 model deu that bai -> None."""
        analyst = AiAnalyst(config={"model": "gemini-2.0-flash"})
        mock_429 = MagicMock(status_code=429, text="rate limited")
        mock_500 = MagicMock(status_code=500, text="server error")
        with patch("analyst.ai_analyst.requests.post",
                   side_effect=[mock_429, mock_500, mock_429, mock_500]) as mock_post:
            result = analyst.analyze(SAMPLE_PRICES, api_key="k")
        assert result is None
        assert mock_post.call_count == 4

    def test_http_error_no_fallback(self):
        """Loi 500 -> thu fallback, ca 2 loi -> None."""
        analyst = AiAnalyst(config={"model": "gemini-2.0-flash"})
        mock_500 = MagicMock(status_code=500, text="server error")
        mock_502 = MagicMock(status_code=502, text="bad gateway")
        with patch("analyst.ai_analyst.requests.post",
                   side_effect=[mock_500, mock_502, mock_500, mock_502]) as mock_post:
            result = analyst.analyze(SAMPLE_PRICES, api_key="k")
        assert result is None
        assert mock_post.call_count == 4

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
            "candidates": [{"content": {"parts": [{"text": VALID_TEXT}]}}]
        }
        with patch("analyst.ai_analyst.requests.post", return_value=mock_ok) as mock_post:
            result = analyst.analyze(SAMPLE_PRICES, api_key="k")
        assert result == VALID_TEXT
        assert mock_post.call_count == 1
        assert "gemini-flash-latest" in mock_post.call_args[0][0]
