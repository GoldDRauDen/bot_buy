# Stock Scanner

Quét và phân tích nguồn dữ liệu chứng khoán (HOSE, HNX, UPCOM).

Pipeline gồm **16 task**, chạy tuần tự qua `main.py`, deterministic, không AI, không scoring — mọi kết luận đều dựa trên bằng chứng thực tế (Evidence First).

## Yêu cầu

- Python **>= 3.10**
- Cài đặt: `pip install -r requirements.txt`

## Cấu trúc

```
stock-scanner/
├── config/
│   ├── sources.yaml    # Danh sách nguồn dữ liệu
│   └── settings.yaml   # Cấu hình ứng dụng (timeout, retry, scheduler, enhancer, reverser)
├── src/
│   ├── scanner/        # Task 1-2, 5: connectivity, discovery, capability
│   ├── crawler/        # Task 3: index crawler
│   ├── builder/        # Task 7: url selector
│   ├── fetcher/        # Task 8: data fetcher
│   ├── validators/     # Task 9-10: schema validator, quality gate
│   ├── reporters/      # Task 11: master report
│   ├── extractor/      # Task 13: data extraction
│   ├── enhancer/       # Task 15: discovery enhancement (SPA/JS)
│   ├── reverser/       # Task 16: API reverse engineering
│   ├── scheduler/      # Task 14: scheduler + incremental update
│   └── utils/          # config_loader, logger, source_loader, source_models
├── tests/              # 309 tests (pytest)
├── output/             # Báo cáo pipeline (xem dưới)
├── history/            # Snapshot lịch sử chạy (Task 14)
├── state/              # Trạng thái scheduler (Task 14)
├── main.py
└── requirements.txt
```

## Pipeline 16 task

| # | Task | Mô tả | Output |
|---|------|-------|--------|
| 1 | Connectivity Test | Kiểm tra kết nối tới từng nguồn | `connectivity_report.json` |
| 2 | Discovery Scan | Tìm endpoint: robots, sitemap, rss, graphql, swagger, openapi | `discovery_report.json` |
| 3 | Index Crawler | Crawl danh sách trang từ sitemap/rss/HTML | `index_pages.json` |
| 5 | Capability Test | Đánh giá capability theo keyword (offline) | `capability_report.json` |
| 7 | URL Selector | Chọn URL cho capability supported | `endpoint_plan.json` |
| 8 | Data Fetcher | Fetch dữ liệu thô (HTTP, có retry) | `raw_data/{source}/{capability}.json` |
| 9 | Schema Validator | Validate cấu trúc dữ liệu | `validated_data/{source}/{capability}.json` |
| 10 | Quality Gate | Đánh giá pass/fail dữ liệu dùng được | `quality_report.json` |
| 11 | Master Report | Tổng hợp toàn pipeline | `final_report.json` |
| 13 | Data Extraction | Trích xuất dữ liệu chuẩn hóa | `extracted_data/{source}/{capability}.json` |
| 14 | Scheduler | Chạy định kỳ, skip task không đổi | `state/pipeline_state.json`, `history/` |
| 15 | Discovery Enhancement | Tìm endpoint thật trong JS bundle/SPA | `enhanced_discovery_report.json` |
| 16 | API Reverse Engineering | Xác định cách gọi API: params, headers, csrf | `endpoint_profiles.json` |

## Cấu hình nguồn (`config/sources.yaml`)

```yaml
sources:
  - name: HOSE
    enabled: true
    type: official
    base_url: https://www.hsx.vn/
    description: Hochi Minh Stock Exchange

  - name: HNX
    enabled: true
    type: official
    base_url: https://www.hnx.vn/
    description: Hanoi Stock Exchange

  - name: UPCOM
    enabled: false
    type: official
    base_url: https://www.hsx.vn/upcom
    description: UPCOM - Unlisted Public Company Market
```

Các field: `name`, `enabled` (true/false), `type`, `base_url`, `description`.

## Chạy

```bash
# Chạy toàn pipeline
python main.py

# Chạy pipeline (scheduler tự quyết định task nào chạy/skip)
# Cấu hình scheduler trong config/settings.yaml:
#   scheduler.interval_minutes  # tần suất chạy định kỳ (cho external scheduler)
#   scheduler.full_scan_every   # scan toàn bộ sau N phút
#   scheduler.force_refresh     # true = chạy tất cả, bỏ qua checksum
```

Scheduler (Task 14) không tự sleep — đặt `interval_minutes` để external scheduler (cron/Task Scheduler) gọi `python main.py` định kỳ.

## Chạy test

```bash
pytest -q          # 309 tests
pytest tests/test_pipeline_integration.py -q   # integration test riêng
```

## Output reports

Tất cả báo cáo trong `output/` (JSON, `ensure_ascii=False`):

| File | Nội dung |
|------|----------|
| `connectivity_report.json` | Kết nối từng nguồn |
| `discovery_report.json` | Endpoint phát hiện được |
| `enhanced_discovery_report.json` | Endpoint từ JS bundle (Task 15) |
| `capability_report.json` | Capability supported/unsupported/unknown |
| `endpoint_profiles.json` | Cách gọi API: method, headers, params (Task 16) |
| `index_pages.json` | Danh sách trang crawl được |
| `endpoint_plan.json` | Kế hoạch fetch URL |
| `raw_data/` | Dữ liệu thô (Task 8) |
| `validated_data/` | Dữ liệu đã validate (Task 9) |
| `quality_report.json` | Quality pass/fail (Task 10) |
| `final_report.json` | Tổng hợp cuối (Task 11) |
| `extracted_data/` | Dữ liệu trích xuất (Task 13) |
| `logs/app.log` | Log chạy |

## Log

Log ghi vào: `output/logs/app.log`
