# instructions.md — Web Console Hardening & Real Data Engineering Loop (F503)

Tracked as **F503** in `Harness/feature_list.json`, Tier: `F5xx`, Dependencies: `F501`, `F401`, `F305`.  
Engineering Methodology: **Loop Engineering (WIP = 1)**.  
`SELECT (1 Item) ➔ EXECUTE (Fix & Code) ➔ VERIFY (Test Command & Real Output) ➔ RECORD (Update Evidence) ➔ NEXT`.

---

## 0. BẢNG TỔNG HỢP NGUYÊN NHÂN GỐC RỄ (ROOT CAUSE AUDIT)

| # | Phân hệ bị lỗi | Hiện tượng (Symptom) | Nguyên nhân gốc rễ (Root Cause) | Giải pháp kỹ thuật (Fix) |
|---|---|---|---|---|
| **1** | **Bot Arena Studio** | `API Error (500): Internal Server Error` khi chat AI | `console_api.py:788` gọi `slm.reason_over_headline(...)`, trong khi method thực tế của `LocalReasoningSLMEngine` là `generate_thesis(...)`. Ngoài ra `slm` bị khởi tạo mới mỗi request. | Chuyển sang `slm.generate_thesis(...)`, dùng singleton `get_slm_engine()` và bọc `try...except HTTPException(503)`. |
| **2** | **Market Dashboard** | Bảng điện và Heatmap trống trơn ("no data") | 1) `console_api.py:325` query `icb_name` & `market_cap` (không tồn tại trong `core.dim_symbol`, cột thật là `industry_name`), gây lỗi Binder Error mà không có `try/except`.<br>2) `get_db_connection()` ưu tiên snapshot DB chỉ có 2 mã, bỏ qua `vesta_ohlcv.duckdb` chứa 4.09 triệu dòng OHLCV và 260K dòng chỉ số! | Cập nhật `get_db_connection()` ưu tiên `vesta_ohlcv.duckdb`, sửa `industry_name`, bọc `try...except` và truy vấn trực tiếp từ `core.market_index_daily`. |
| **3** | **Navbar & Ngôn ngữ** | Trộn lẫn Anh-Việt, thừa chip `NODE: PROD :8899 \| 10M VND / BOT` | Chưa có tầng i18n, các chuỗi text bị hardcode rải rác inline trong component. | Xây dựng `web/src/i18n.ts` + `LangContext.tsx`, xóa chip debug, thêm nút chuyển đổi `VI / EN` có icon `Languages`. |
| **4** | **Typography Headline** | Font headline bị vỡ dấu tiếng Việt (clipping) | `lineHeight: 1.15` ở `OverviewPage.tsx:86` quá hẹp so với nguyên tắc dấu thanh tiếng Việt (cần $\ge 1.48$). | Định nghĩa `--lh-tight: 1.48;` và `--lh-body: 1.65;` trong `index.css`, chuẩn hóa toàn bộ headline. |
| **5** | **Model Feedback** | Trang trống khi mới vào ("cant see anything") | `result` khởi tạo là `null`, không tự chấm điểm trên `mount`, và lỗi chỉ báo qua native `alert()`. | Kích hoạt `handleScore()` ngay khi mount (`useEffect`), thay `alert()` bằng thẻ báo lỗi `panel-error` trực quan. |
| **6** | **Data Integrity** | Dữ liệu chỉ số và Regime F203 bị hardcode tĩnh | `console_api.py:284` và `TickerStrip.tsx` dùng mảng số cố định (`1288.45`, `1352.18`). `regime_matrix` không đọc file báo cáo F203. | Đọc `core.market_index_daily` thời gian thực; đọc `out/f203_regime_report.json` và gắn cờ `source: unavailable` nếu thiếu dữ liệu. |

---

## 1. LOOP ENGINEERING WORKFLOW (WIP = 1)

### [ ] BƯỚC 1: SỬA LỖI 500 BOT ARENA AI CHAT (F503-A)
- **Mục tiêu**: Xử lý triệt để lỗi 500 khi người dùng chat với Qwen-2.5-3B CoT Assistant.
- **Thực thi trong `src/service/console_api.py`**:
  1. Khởi tạo Singleton `_slm_engine` ở cấp module.
  2. Sửa lệnh gọi `slm.reason_over_headline(...)` thành `slm.generate_thesis(...)`.
  3. Bọc ngoại lệ với mã lỗi HTTP 503 và thông báo rõ ràng nếu mô hình hoặc Ollama offline.
- **Code mẫu**:
```python
_slm_engine: Optional[LocalReasoningSLMEngine] = None

def get_slm_engine() -> LocalReasoningSLMEngine:
    global _slm_engine
    if _slm_engine is None:
        _slm_engine = LocalReasoningSLMEngine()
    return _slm_engine

@app.post("/api/bot-arena/chat", tags=["Bot Arena AI Studio"])
def chat_ai_strategy_studio(req: AIChatRequest):
    try:
        slm = get_slm_engine()
        res = slm.generate_thesis(
            headline=req.message,
            symbol="VN30F1M",
            source="user_strategy",
            source_weight=1.0,
            fast_path_sentiment="NEUTRAL",
            fast_path_alpha=50.0,
        )
    except Exception as exc:
        logger.exception("bot-arena/chat failed")
        raise HTTPException(status_code=503, detail=f"SLM Engine không khả dụng: {exc}")
    
    # Sinh cấu hình bot...
    return {"reply": res.reasoning_chain, "bot": custom_bot}
```
- **Lệnh kiểm chứng (Verification)**:
```bash
python -c "from fastapi.testclient import TestClient; from src.service.console_api import app; c = TestClient(app); r = c.post('/api/bot-arena/chat', json={'message': 'Chiến lược phòng thủ'}); print(r.status_code, r.json().get('bot', {}).get('bot_id'))"
```
- **Evidence**: `[ ] Chờ dán kết quả thực thi...`

---

### [ ] BƯỚC 2: KHẮC PHỤC TRIỆT ĐỂ BẢNG ĐIỆN & HEATMAP "NO DATA" (F503-B)
- **Mục tiêu**: Nạp dữ liệu thị trường từ CSDL `db/vesta_ohlcv.duckdb` (4.09M dòng OHLCV và 260K dòng Index).
- **Thực thi trong `src/service/console_api.py`**:
  1. Cập nhật `get_db_connection()`: Ưu tiên `db/vesta_ohlcv.duckdb` lên vị trí đầu tiên.
  2. Sửa câu lệnh Heatmap: Đổi `COALESCE(icb_name, 'Khác')` thành `COALESCE(industry_name, 'Khác')`, xóa `market_cap` (thay bằng `5000.0`).
  3. Bọc toàn bộ truy vấn `get_market_heatmap` trong `try...except` trả về `{"date": latest_date, "count": len(items), "data": items, "error": None}`.
  4. Lấy chỉ số thị trường thực từ `core.market_index_daily` cho ngày giao dịch mới nhất (`VNINDEX`, `VN30`, `HNX-INDEX`, `UPCOM-INDEX`).
- **Code mẫu truy vấn chỉ số thực**:
```python
# Trong get_dashboard_overview():
indices_rows = con.execute("""
    SELECT index_code, close, (close - open) / NULLIF(open, 0) * 100.0, (close - open)
    FROM core.market_index_daily
    WHERE date = (SELECT MAX(date) FROM core.market_index_daily)
      AND index_code IN ('VNINDEX', 'VN30', 'HNX-INDEX', 'UPCOM-INDEX')
""").fetchall()
```
- **Lệnh kiểm chứng (Verification)**:
```bash
python -c "from fastapi.testclient import TestClient; from src.service.console_api import app; c = TestClient(app); r1 = c.get('/api/dashboard/overview'); r2 = c.get('/api/dashboard/heatmap'); print('Overview indices:', len(r1.json().get('indices', []))); print('Heatmap items:', len(r2.json().get('data', [])))"
```
- **Evidence**: `[ ] Chờ dán kết quả thực thi...`

---

### [ ] BƯỚC 3: XÓA CHIP DEBUG & XÂY DỰNG CHUYỂN ĐỔI NGÔN NGỮ VI/EN (F503-C)
- **Mục tiêu**: Xóa `NODE: PROD :8899 | 10M VND / BOT` trên Navbar, thêm bộ chuyển đổi ngôn ngữ Anh - Việt mượt mà.
- **Thực thi Frontend**:
  1. Tạo `web/src/i18n.ts`: Định nghĩa từ điển đa ngôn ngữ cho toàn bộ nhãn điều hướng, tiêu đề trang và nút bấm.
  2. Tạo `web/src/LangContext.tsx`: `LangProvider` với `localStorage.getItem('vesta-lang')`.
  3. Bọc `<App />` trong `<LangProvider>` tại `web/src/main.tsx`.
  4. Cập nhật `web/src/components/Navbar.tsx`:
     - Xóa khối `<span className="badge badge-teal mono">NODE: PROD :8899</span>` và `<span className="badge badge-gold">10M VND / BOT</span>`.
     - Thêm button chuyển đổi ngôn ngữ với icon `Languages`.
- **Code mẫu `Navbar.tsx`**:
```tsx
const { lang, t, toggle } = useLang();

<button 
  onClick={toggle} 
  className="btn-ghost" 
  style={{ padding: '4px 8px', fontSize: '11px', display: 'flex', alignItems: 'center', gap: '5px' }}
  title="Switch Language / Chuyển đổi ngôn ngữ"
>
  <Languages size={13} color="var(--gold)" />
  <span className="mono" style={{ fontWeight: 700 }}>{lang.toUpperCase()}</span>
</button>
```
- **Lệnh kiểm chứng (Verification)**:
```bash
npm run build --prefix web && grep -rn "PROD :8899" web/dist/ || echo "CLEAN: Debug chips removed"
```
- **Evidence**: `[ ] Chờ dán kết quả thực thi...`

---

### [ ] BƯỚC 4: CHUẨN HÓA TYPOGRAPHY & LINE-HEIGHT TIẾNG VIỆT (F503-D)
- **Mục tiêu**: Khắc phục hiện tượng clipping dấu hỏi, ngã, nặng, mũ trong tiếng Việt khi hiển thị headline lớn.
- **Thực thi trong `web/src/index.css`**:
  ```css
  :root {
    --lh-tight: 1.48; /* Chuẩn an toàn tuyệt đối cho heading tiếng Việt có dấu kép */
    --lh-normal: 1.60;
    --lh-body: 1.68;
  }
  h1, h2, h3, .sans-headline {
    line-height: var(--lh-tight) !important;
  }
  ```
- **Cập nhật `OverviewPage.tsx`**: Sửa dòng 86 từ `lineHeight: 1.15` thành `lineHeight: 'var(--lh-tight)'`.
- **Lệnh kiểm chứng**: Kiểm tra trực quan trên trình duyệt với các chuỗi tiếng Việt như: `"NƠI THỊ TRƯỜNG GẶP GỠ MÔ HÌNH TOÁN LƯỢNG TÀI CHÍNH"`.
- **Evidence**: `[ ] Chờ dán kết quả thực thi...`

---

### [ ] BƯỚC 5: NÂNG CẤP TRANG MODEL FEEDBACK VỚI AUTO-SCORE & INLINE ERROR (F503-E)
- **Mục tiêu**: Người dùng khi vừa mở trang Phản Hồi Mô Hình sẽ lập tức nhìn thấy kết quả phân tích mẫu thay vì trang trống; nếu có lỗi sẽ hiển thị hộp thoại cảnh báo thay vì `alert()`.
- **Thực thi trong `web/src/pages/FeedbackPage.tsx`**:
  1. Thêm `useEffect(() => { handleScore(); }, [])` để tự động chấm điểm tiêu đề mặc định khi load trang.
  2. Thêm state `error: string | null`.
  3. Thay `alert(...)` bằng hiển thị lỗi trực tiếp trên giao diện:
     ```tsx
     {error && (
       <div className="panel" style={{ borderColor: 'var(--red)', padding: '14px', marginBottom: '16px', background: 'rgba(239, 68, 68, 0.08)' }}>
         <div style={{ color: 'var(--red)', fontSize: '12px', fontWeight: 600 }}>⚠ LỖI SUY LUẬN MÔ HÌNH: {error}</div>
       </div>
     )}
     ```
- **Lệnh kiểm chứng (Verification)**:
```bash
npm run build --prefix web
```
- **Evidence**: `[ ] Chờ dán kết quả thực thi...`

---

### [ ] BƯỚC 6: XÓA DỮ LIỆU FAKE & KẾT NỐI BÁO CÁO F203 THỰC TẾ (F503-F)
- **Mục tiêu**: Đảm bảo nguyên tắc bảo toàn tính trung thực của số liệu (B3: Numbers Need a Source).
- **Thực thi trong `src/service/console_api.py`**:
  1. Xóa mảng hardcode tĩnh trong `get_f203_regimes()`. Đọc trực tiếp từ file báo cáo `out/f203_regime_report.json`.
  2. Nếu file chưa tồn tại, trả về `{"total_regimes": 0, "status": "PENDING_AUDIT", "audited_regimes": [], "message": "Chưa có báo cáo F203"}` thay vì bịa ra số liệu lợi nhuận.
  3. Xóa fallback `defaultIndices` trong `TickerStrip.tsx`. Nhận `indices` trực tiếp từ `App.tsx`.
- **Lệnh kiểm chứng (Verification)**:
```bash
python -c "from fastapi.testclient import TestClient; from src.service.console_api import app; c = TestClient(app); r = c.get('/api/preprocessing/regimes'); print('F203 status:', r.json().get('status', 'OK'))"
```
- **Evidence**: `[ ] Chờ dán kết quả thực thi...`

---

## 2. NHẬT KÝ KIỂM CHỨNG & BÀN GIAO (EVIDENCE LOG)

- [ ] **F503-A (Bot Arena 500 Fix)**: Chưa kiểm chứng.
- [ ] **F503-B (Market Dashboard Real Data)**: Chưa kiểm chứng.
- [ ] **F503-C (Navbar & i18n Switch)**: Chưa kiểm chứng.
- [ ] **F503-D (Typography Line-Height)**: Chưa kiểm chứng.
- [ ] **F503-E (Model Feedback Auto-Score)**: Chưa kiểm chứng.
- [ ] **F503-F (Eliminate Fabricated Paths)**: Chưa kiểm chứng.
