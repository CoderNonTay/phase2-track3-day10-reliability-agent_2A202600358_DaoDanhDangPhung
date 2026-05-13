# Báo Cáo Lab Day 10 - Độ Tin Cậy Agent

## Thông tin học viên

- Họ và tên: **Đào Danh Đăng Phụng**
- Mã học viên: **2A202600358**

## 1. Tóm tắt kiến trúc

Hệ thống gateway triển khai theo mô hình nhiều lớp độ tin cậy: kiểm tra cache trước, gọi provider qua circuit breaker theo thứ tự ưu tiên, và trả về static fallback khi toàn bộ provider không khả dụng. Mỗi phản hồi đều có `route` và `route_reason` để truy vết đường đi khi chaos test.

```text
User Request
    |
    v
[Gateway] ---> [Cache check] ---> HIT? return cached
    |                                 |
    v                                 v MISS
[Circuit Breaker: Primary] -------> Provider A
    |  (OPEN? skip)
    v
[Circuit Breaker: Backup] --------> Provider B
    |  (OPEN? skip)
    v
[Static fallback message]
```

## 2. Cấu hình và lý do chọn

| Tham số | Giá trị | Lý do |
|---|---:|---|
| failure_threshold | 3 | Mở mạch đủ nhanh khi lỗi liên tục nhưng không quá nhạy với nhiễu ngắn hạn. |
| reset_timeout_seconds | 2 | Thời gian chờ ngắn, phù hợp môi trường mô phỏng để kiểm tra phục hồi nhanh. |
| success_threshold | 1 | Chỉ cần 1 probe thành công để đóng lại mạch HALF_OPEN. |
| cache TTL | 300 | Cân bằng giữa độ tươi dữ liệu và tỷ lệ cache hit cho nhóm truy vấn dạng FAQ/policy. |
| similarity_threshold | 0.92 | Ngưỡng cao giúp giảm false-hit cho truy vấn nhạy về năm (2024/2026). |
| load_test requests | 100 / scenario | Đủ lớn để ổn định metric, vẫn chạy nhanh trong máy local. |

## 3. Định nghĩa SLO

| SLI | Mục tiêu SLO | Giá trị thực tế | Đạt? |
|---|---|---:|---|
| Availability | >= 99% | 98.75% | Không |
| Latency P95 | < 2500 ms | 484.84 ms | Có |
| Fallback success rate | >= 95% | 94.51% | Không |
| Cache hit rate | >= 10% | 62.75% | Có |
| Recovery time | < 5000 ms | 4466.67 ms | Có |

## 4. Metrics tổng hợp

Nguồn dữ liệu: `reports/metrics.json`

| Metric | Value |
|---|---:|
| total_requests | 400 |
| availability | 0.9875 |
| error_rate | 0.0125 |
| latency_p50_ms | 0.13 |
| latency_p95_ms | 484.84 |
| latency_p99_ms | 535.18 |
| fallback_success_rate | 0.9451 |
| cache_hit_rate | 0.6275 |
| circuit_open_count | 10 |
| recovery_time_ms | 4466.6744867960615 |
| estimated_cost | 0.06194 |
| estimated_cost_saved | 0.251 |

## 5. So sánh có cache và không cache

Nguồn dữ liệu:
- Có cache: `reports/metrics_with_cache.json`
- Không cache: `reports/metrics_no_cache.json`

| Metric | Không cache | Có cache | Delta |
|---|---:|---:|---:|
| latency_p50_ms | 269.25 | 0.13 | -269.12 |
| latency_p95_ms | 504.97 | 483.80 | -21.17 |
| estimated_cost | 0.170002 | 0.061940 | -0.108062 |
| cache_hit_rate | 0.0 | 0.6275 | +0.6275 |

## 6. Redis shared cache

- Vì sao in-memory cache chưa đủ cho production nhiều instance:
  mỗi instance giữ cache riêng trong RAM, nên hit ở instance A không dùng lại được ở instance B.
- SharedRedisCache giải quyết bằng cách:
  lưu cache chung trong Redis theo key hash + TTL, cho phép nhiều instance truy cập cùng một trạng thái cache.

### Bằng chứng shared state

Kết quả chạy thực tế với 2 instance `SharedRedisCache`:

```text
('shared response value', 1.0)
```

Giải thích: instance thứ 2 đọc được entry do instance thứ 1 ghi, score exact match = 1.0.

### Redis key thực tế

```text
['rl:report:d7978f530864']
```

## 7. Kịch bản chaos

| Kịch bản | Kỳ vọng | Quan sát | Kết quả |
|---|---|---|---|
| primary_timeout_100 | Primary lỗi 100%, backup phục vụ, circuit mở | fallback hoạt động, có open events, pass theo rule | Pass |
| primary_flaky_50 | Circuit dao động, vừa primary vừa fallback | có open events, availability đạt ngưỡng | Pass |
| all_healthy | Hệ thống ổn định, không mở circuit | availability cao, pass theo rule | Pass |
| cache_stale_candidate | Không false-hit giữa truy vấn khác năm | guardrail chặn false-hit 2024/2026 | Pass |

## 8. Phân tích rủi ro còn lại

Điểm yếu còn lại: trạng thái circuit breaker hiện vẫn theo từng process, chưa đồng bộ giữa nhiều instance. Trong hệ thống scale ngang, có thể xảy ra tình trạng một instance đã OPEN nhưng instance khác vẫn tiếp tục gọi provider lỗi.

Hướng cải tiến trước production:
- Đồng bộ circuit state trên Redis (counters/state/TTL),
- Dùng thao tác atomic để tránh race condition khi nhiều instance cập nhật cùng lúc.

## 9. Hướng phát triển tiếp theo

1. Triển khai Redis-backed circuit state để nhất quán đa instance.
2. Thêm chạy tải đồng thời (thread pool) để đo hành vi dưới concurrent load.
3. Export metric theo Prometheus để giám sát runtime thực tế.
