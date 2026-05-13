# Day 10 Lab - Reliability Engineering for Production Agents

Bài lab xây dựng reliability layer cho một LLM gateway theo kiểu production: circuit breaker, fallback, cache (in-memory và Redis shared cache), metrics và chaos scenarios.

## Thông tin học viên

- Họ và tên: **Đào Danh Đăng Phụng**
- Mã học viên: **2A202600358**

## Mục tiêu học tập

Sau bài này, bạn cần đạt được:

1. Triển khai circuit breaker đầy đủ 3 trạng thái.
2. Route qua fallback chain có lý do route rõ ràng.
3. Cache có TTL + guardrail an toàn để tránh false-hit.
4. Shared Redis cache cho multi-instance.
5. Thu thập metrics: availability, error_rate, P50/P95/P99, fallback_success_rate, cache_hit_rate, recovery_time, estimated_cost_saved.
6. Tạo báo cáo có số liệu có thể tái lập.

## Cấu trúc quan trọng

```text
src/reliability_lab/
  circuit_breaker.py
  gateway.py
  cache.py
  chaos.py
  metrics.py
  config.py

tests/
  test_gateway_contract.py
  test_metrics.py
  test_config.py
  test_todo_requirements.py
  test_redis_cache.py

reports/
  metrics.json
  metrics_with_cache.json
  metrics_no_cache.json
  final_report.md
  report_template.md
```

## Hướng dẫn chạy lab trên máy bạn (không cần Docker)

Lab này không cần API key. Redis có thể chạy local memory (WSL/native), miễn là có endpoint `redis://localhost:6379/0`.

### 1) Chuẩn bị Redis local

Nếu dùng WSL Ubuntu:

```bash
sudo apt update
sudo apt install -y redis-server
sudo service redis-server start
redis-cli ping
```

Kỳ vọng: `PONG`.

### 2) Cài dependencies Python (PowerShell Windows)

```powershell
python -m pip install -e ".[dev]"
```

### 3) Kiểm tra Redis từ Python

```powershell
python -c "import redis; print(redis.Redis.from_url('redis://localhost:6379/0').ping())"
```

Kỳ vọng: `True`.

### 4) Chạy test Redis riêng

```powershell
python -m pytest -q tests/test_redis_cache.py
```

Kỳ vọng: 6 tests pass, không skipped.

### 5) Chạy full test suite

```powershell
python -m pytest -q
```

Trạng thái hiện tại của repo này:

- `11 passed, 1 xpassed`
- `xpassed` ở đây là bình thường vì test đánh dấu `xfail` đã được fix tốt hơn kỳ vọng.

### 6) Chạy lint + typecheck

```powershell
python -m ruff check src tests scripts
python -m mypy src --show-error-codes --pretty
```

### 7) Sinh metrics và report

```powershell
$env:PYTHONPATH='src'
python scripts/run_chaos.py --config configs/default.yaml --out reports/metrics.json
python scripts/generate_report.py --metrics reports/metrics.json --out reports/final_report.md
```

### 8) Sinh thêm metrics so sánh cache on/off

```powershell
$env:PYTHONPATH='src'
python - <<'PY'
import copy
from reliability_lab.chaos import load_queries, run_simulation
from reliability_lab.config import load_config

cfg = load_config('configs/default.yaml')
queries = load_queries()

m_on = run_simulation(cfg, queries)
m_on.write_json('reports/metrics_with_cache.json')

cfg_off = copy.deepcopy(cfg)
cfg_off.cache.enabled = False
m_off = run_simulation(cfg_off, queries)
m_off.write_json('reports/metrics_no_cache.json')
PY
```

## Báo cáo nằm ở đâu?

Tất cả file nộp nằm trong thư mục `reports/`:

- `reports/metrics.json`: metrics chính
- `reports/metrics_with_cache.json`: metrics khi bật cache
- `reports/metrics_no_cache.json`: metrics khi tắt cache
- `reports/final_report.md`: báo cáo cuối cùng
- `reports/report_template.md`: mẫu báo cáo tiếng Việt

## Checklist nộp bài

1. Code TODO đã hoàn thành trong `src/reliability_lab/`.
2. `python -m pytest -q` pass (Redis tests không skipped).
3. `python -m ruff check ...` pass.
4. `python -m mypy src ...` pass.
5. Có đủ 3+ chaos scenarios và metrics reproducible.
6. Báo cáo `reports/final_report.md` có đầy đủ số liệu và phân tích.
