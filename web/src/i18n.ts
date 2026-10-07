export type Language = 'vi' | 'en';

export interface TierInfo {
  name: string;
  desc: string;
  actionLabel: string;
}

export interface Translations {
  nav: {
    overview: string;
    dashboard: string;
    crawler: string;
    preprocessing: string;
    feedback: string;
    arena: string;
    lang_btn: string;
  };
  common: {
    healthy: string;
    unhealthy: string;
    loading: string;
    error: string;
    search: string;
    refresh: string;
    close: string;
    prev: string;
    next: string;
    page: string;
    of: string;
    all: string;
  };
  overview: {
    badge: string;
    title: string;
    subtitle: string;
    btn_dashboard: string;
    btn_arena: string;
    btn_crawler: string;
    live_model_feed: string;
    prod_badge: string;
    dir_acc: string;
    peak_sharpe: string;
    latency: string;
    arch_title: string;
    arch_subtitle: string;
    status_badge: string;
    tiers: TierInfo[];
  };
  dashboard: {
    title: string;
    subtitle: string;
    live_badge: string;
    real_data: string;
    advancing: string;
    declining: string;
    unchanged: string;
    ceiling: string;
    floor: string;
    trading_val: string;
    foreign_net: string;
    heatmap_title: string;
    by_val: string;
    by_cap: string;
    all_sectors: string;
    candlestick_title: string;
    search_ticker_placeholder: string;
    select_timeframe: string;
    foreign_flow_title: string;
    corporate_events_title: string;
    financial_news_title: string;
    search_news_placeholder: string;
    no_events: string;
    no_news: string;
    loading_news: string;
    read_more: string;
    collapse: string;
    date: string;
    buy_bil: string;
    sell_bil: string;
    net_bil: string;
  };
  crawler: {
    title: string;
    subtitle: string;
    check_status: string;
    atomic_ingest: string;
    config_title: string;
    mode_latest: string;
    mode_category: string;
    mode_all: string;
    category_label: string;
    scope_label: string;
    scope_all: string;
    scope_vn30: string;
    scope_hose: string;
    scope_hnx: string;
    delay_label: string;
    buffer_label: string;
    start_btn: string;
    stop_btn: string;
    lakehouse_status_title: string;
    th_category: string;
    th_records: string;
    th_symbols: string;
    th_date_range: string;
    th_status: string;
    terminal_title: string;
    auto_scroll: string;
    terminal_ready: string;
  };
  preprocessing: {
    title: string;
    subtitle: string;
    dsr_badge: string;
    pbo_badge: string;
    dag_title: string;
    regime_title: string;
    sign_flip_badge: string;
    audit_desc: string;
    th_regime_code: string;
    th_scenario: string;
    th_hose: string;
    th_hnx: string;
    th_upcom: string;
    th_sign_flip: string;
    th_risk_rule: string;
    sign_flip_alert: string;
    normal_status: string;
  };
  feedback: {
    title: string;
    subtitle: string;
    cb_badge: string;
    sandbox_title: string;
    sub15_badge: string;
    input_label: string;
    symbol_label: string;
    source_label: string;
    score_now: string;
    scoring: string;
    latency: string;
    sentiment_class: string;
    alpha_score: string;
    recommendation: string;
    consistency_check: string;
    consistent: string;
    violation: string;
    thesis_title: string;
    drift_title: string;
    window_info: string;
    dir_acc: string;
    spearman_ic: string;
    brier_score: string;
    cb_state: string;
  };
  arena: {
    title: string;
    subtitle: string;
    capital_badge: string;
    oddlot_badge: string;
    total_bots_card: string;
    ai_twins_desc: string;
    initial_cash_card: string;
    nav_cap_desc: string;
    asset_class_card: string;
    multi_asset_desc: string;
    pbo_card: string;
    pbo_desc: string;
    leaderboard_title: string;
    filter_all: string;
    filter_ai: string;
    filter_non_ai: string;
    th_rank: string;
    th_bot_id: string;
    th_strategy: string;
    th_model: string;
    th_sharpe: string;
    th_return: string;
    th_maxdd: string;
    th_winrate: string;
    studio_title: string;
    slm_badge: string;
    welcome_msg: string;
    reasoning_in_progress: string;
    chat_placeholder: string;
    generated_config: string;
    target_assets: string;
    signal_weights: string;
    sharpe_forecast: string;
    rec_action: string;
    dynamic_ranking_active: string;
    reset_overall_ranking: string;
    ranking_source_note: string;
    th_action: string;
  };
}

export const translations: Record<Language, Translations> = {
  vi: {
    nav: {
      overview: 'Tổng Quan',
      dashboard: 'Bảng Điện Thị Trường',
      crawler: 'Thu Thập Dữ Liệu',
      preprocessing: 'Tiền Xử Lý & QA',
      feedback: 'Phản Hồi Mô Hình',
      arena: 'Đấu Trường Bot',
      lang_btn: 'VI',
    },
    common: {
      healthy: 'HỆ THỐNG HOẠT ĐỘNG TỐT',
      unhealthy: 'MẤT KẾT NỐI HỆ THỐNG',
      loading: 'Đang nạp dữ liệu...',
      error: 'Lỗi',
      search: 'Tìm kiếm mã...',
      refresh: 'Làm mới',
      close: 'Đóng',
      prev: 'Trang trước',
      next: 'Trang sau',
      page: 'Trang',
      of: 'trên',
      all: 'Tất cả',
    },
    overview: {
      badge: 'KIẾN TRÚC GIAO DỊCH TỰ ĐỘNG THẾ HỆ MỚI',
      title: 'Hệ Thống Phân Tích Định Lượng & Suy Luận Đa Phương Thức VESTA',
      subtitle: 'Nền tảng giao dịch tự động kết hợp xử lý hồ dữ liệu DuckDB, mô hình PhoBERT tài chính, kiểm định nhất quán Kolmogorov Simplex-TCD và đấu trường mô phỏng vi cấu trúc 308 Bot.',
      btn_dashboard: 'Vào Bảng Điện Thị Trường',
      btn_arena: 'Khám Phá Đấu Trường Bot',
      btn_crawler: 'Điều Khiển Thu Thập Dữ Liệu',
      live_model_feed: 'Luồng Giám Sát Mô Hình Trực Tiếp',
      prod_badge: 'MÔ HÌNH VẬN HÀNH',
      dir_acc: 'ĐỘ CHÍNH XÁC',
      peak_sharpe: 'SHARPE TỐI ĐA',
      latency: 'ĐỘ TRỄ',
      arch_title: 'Các Tầng Kiến Trúc Hệ Thống VESTA',
      arch_subtitle: 'Chuỗi quy trình hoàn chỉnh từ hồ dữ liệu DuckDB đến mô hình AI và đấu trường bot chiến lược',
      status_badge: 'HỆ THỐNG ĐÃ SẴN SÀNG',
      tiers: [
        {
          name: 'Thu Thập Hồ Dữ Liệu',
          desc: '13 phân hệ DuckDB: Giá nến OHLCV 1 phút và ngày, Báo cáo tài chính, Thuyết minh, Tin tức CafeF, Phái sinh VN30F, Quỹ ETF và Trái phiếu HNX.',
          actionLabel: 'Mở Bảng Điều Khiển Thu Thập →',
        },
        {
          name: 'Tiền Xử Lý Chuẩn Điểm Thời Gian',
          desc: 'Quy trình kết nối dữ liệu chuẩn xác không rò rỉ tương lai (0% Look-ahead bias), kiểm toán chất lượng 11 chiều và phân giải danh tính cổ đông lớn.',
          actionLabel: 'Xem Quy Trình Kiểm Định QA →',
        },
        {
          name: 'Kiểm Định Kinh Lượng & Rào Chắn',
          desc: 'Kiểm toán phương pháp Bootstrap đa chiều, tỷ số Sharpe hiệu chỉnh DSR/PBO theo chuẩn mực học thuật, và ma trận 16 trạng thái thị trường.',
          actionLabel: 'Xem Ma Trận Trạng Thái Thị Trường →',
        },
        {
          name: 'Mô Hình Hóa Đa Nhân Tố & Nhất Quán',
          desc: 'PhoBERT tài chính tinh chỉnh, mạng nơ-ron tích hợp đa phương thức Cross-Attention, cổng chiếu Kolmogorov Simplex-TCD và mô hình chuỗi tư duy SLM CoT.',
          actionLabel: 'Thử Nghiệm Chấm Điểm AI →',
        },
        {
          name: 'Dịch Vụ Suy Luận & Kiểm Soát Trôi Dạt',
          desc: 'Dịch vụ suy luận streaming độ trễ siêu tốc dưới 15ms, khử trùng lặp tin tức Simhash, giám sát trôi dạt phân phối và ngắt mạch tự động.',
          actionLabel: 'Kiểm Tra Giám Sát Trôi Dạt →',
        },
        {
          name: 'Đấu Trường Chiến Lược Đa Bot',
          desc: 'Đấu trường 308 bot chiến lược với vốn khởi điểm 10 triệu VNĐ, khớp lô lẻ (Odd-lot 1-99), 5 kịch bản Monte Carlo và bộ sinh bot tự động.',
          actionLabel: 'Vào Đấu Trường 308 Bot →',
        },
      ],
    },
    dashboard: {
      title: 'Bảng Điện & Chỉ Số Thị Trường Tổng Hợp',
      subtitle: 'Dữ liệu thời gian thực đồng bộ từ Lakehouse DuckDB: VN-Index, VN30, HNX, UPCOM và Bản đồ nhiệt thanh khoản ngành.',
      live_badge: 'THỊ TRƯỜNG TRỰC TIẾP',
      real_data: 'DỮ LIỆU THỰC TẾ (LAKEHOUSE)',
      advancing: 'Tăng giá',
      declining: 'Giảm giá',
      unchanged: 'Đứng giá',
      ceiling: 'Tăng trần',
      floor: 'Giảm sàn',
      trading_val: 'Tổng GTGD',
      foreign_net: 'Khối ngoại ròng',
      heatmap_title: 'Bản Đồ Nhiệt Thị Trường Theo Thanh Khoản',
      by_val: 'Theo Giá Trị GD',
      by_cap: 'Theo Vốn Hóa',
      all_sectors: 'Tất Cả Các Ngành',
      candlestick_title: 'Biểu Đồ Nến Kỹ Thuật',
      search_ticker_placeholder: 'Tìm kiếm hoặc nhập mã CP (ví dụ: FPT, VIC, VCB)...',
      select_timeframe: 'Khung thời gian',
      foreign_flow_title: 'Dòng Tiền Khối Ngoại (20 Phiên Gần Nhất)',
      corporate_events_title: 'Lịch Sự Kiện Doanh Nghiệp & ĐHĐCĐ',
      financial_news_title: 'Dòng Tin Tức Tài Chính Thời Gian Thực (Lakehouse vesta_news)',
      search_news_placeholder: 'Lọc tin tức theo từ khóa hoặc tiêu đề...',
      no_events: 'Không ghi nhận sự kiện quyền trong khoảng thời gian này.',
      no_news: 'Không tìm thấy bài viết tin tức phù hợp.',
      loading_news: 'Đang tải dòng tin tức tài chính...',
      read_more: 'Xem toàn bộ nội dung bài viết ▼',
      collapse: 'Thu gọn nội dung ▲',
      date: 'Ngày',
      buy_bil: 'Mua (Tỷ)',
      sell_bil: 'Bán (Tỷ)',
      net_bil: 'Ròng (Tỷ)',
    },
    crawler: {
      title: 'Bộ Điều Phối Thu Thập Dữ Liệu Lakehouse',
      subtitle: 'Nền tảng kiểm soát thu thập dữ liệu tự động, hỗ trợ cơ chế đệm phi khóa và nạp nguyên tử an toàn vào DuckDB',
      check_status: 'Kiểm Tra Lakehouse',
      atomic_ingest: 'Nạp Nguyên Tử (Atomic Ingest)',
      config_title: 'Cấu Hình Lệnh Thu Thập Dữ Liệu',
      mode_latest: '1. Cập Nhật Mới Nhất',
      mode_category: '2. Theo Phân Hệ',
      mode_all: '3. Toàn Bộ Lịch Sử',
      category_label: 'Phân hệ dữ liệu:',
      scope_label: 'Phạm vi cổ phiếu:',
      scope_all: 'Toàn Bộ Thị Trường (~1,820 mã)',
      scope_vn30: 'Rổ Chỉ Số VN30 (30 mã Bluechips)',
      scope_hose: 'Sàn HOSE (~400 mã)',
      scope_hnx: 'Sàn HNX (~320 mã)',
      delay_label: 'Độ trễ cào & Số trang:',
      buffer_label: 'Bộ đệm phi khóa (Zero-Lock Buffer)',
      start_btn: 'BẮT ĐẦU THU THẬP',
      stop_btn: 'DỪNG TIẾN TRÌNH',
      lakehouse_status_title: 'Tình Trạng 13 Phân Hệ Hồ Dữ Liệu DuckDB',
      th_category: 'Phân Hệ',
      th_records: 'Số Bản Ghi',
      th_symbols: 'Số Mã',
      th_date_range: 'Khoảng Thời Gian',
      th_status: 'Trạng Thái',
      terminal_title: 'Cửa Sổ Dòng Nhật Ký (SSE Live Stream)',
      auto_scroll: 'Tự động cuộn',
      terminal_ready: '[Sẵn sàng] Không có tiến trình thu thập nào đang chạy. Nhấn "BẮT ĐẦU THU THẬP" để khởi động...',
    },
    preprocessing: {
      title: 'Tiền Xử Lý Dữ Liệu & Kiểm Định Kinh Lượng Học',
      subtitle: 'Bảo đảm tuyệt đối chuẩn 0% rò rỉ tương lai (Look-ahead Free), kiểm toán chất lượng 11 chiều và ma trận trạng thái thị trường',
      dsr_badge: 'DSR = 0.942 (ĐẠT CHUẨN)',
      pbo_badge: 'PBO = 4.8% (AN TOÀN)',
      dag_title: 'Quy Trình Dòng Dữ Liệu Chuẩn Điểm Thời Gian (Point-in-Time Pipeline DAG)',
      regime_title: 'Ma Trận 16 Chế Độ Thị Trường × 3 Sàn Giao Dịch',
      sign_flip_badge: 'CẢNH BÁO ĐẢO DẤU (SIGN-FLIP)',
      audit_desc: 'Quy tắc kiểm toán vi cấu trúc: Phát hiện các giai đoạn mà tín hiệu đảo chiều bị đảo dấu âm. Trong các giai đoạn khủng hoảng thanh khoản, hệ thống kích hoạt rào chắn ngắt mạch an toàn để từ chối các lệnh mua bắt đáy rủi ro.',
      th_regime_code: 'Mã Chế Độ',
      th_scenario: 'Tên Kịch Bản Thị Trường',
      th_hose: 'HOSE (Alpha)',
      th_hnx: 'HNX (Alpha)',
      th_upcom: 'UPCOM (Alpha)',
      th_sign_flip: 'Hiện Tượng Đảo Dấu',
      th_risk_rule: 'Quy Tắc Quản Trị Rủi Ro',
      sign_flip_alert: 'ĐẢO DẤU ÂM (SIGN-FLIP)',
      normal_status: 'CHUẨN TẮC',
    },
    feedback: {
      title: 'Phản Hồi Mô Hình AI & Kiểm Soát Trôi Dạt Phân Phối',
      subtitle: 'Hệ thống suy luận streaming siêu tốc dưới 15ms, kiểm định Kolmogorov Simplex-TCD và chuỗi tư duy mô hình ngôn ngữ nhỏ SLM CoT',
      cb_badge: 'TRẠNG THÁI NGẮT MẠCH',
      sandbox_title: 'Chấm Điểm Tin Tức Thời Gian Thực (Inference Sandbox)',
      sub15_badge: 'ĐỘ TRỄ DƯỚI 15MS',
      input_label: 'Nhập tiêu đề tin tức tài chính tiếng Việt hoặc chọn mẫu có sẵn:',
      symbol_label: 'Mã CP:',
      source_label: 'Nguồn tin:',
      score_now: 'CHẤM ĐIỂM NGAY',
      scoring: 'ĐANG SUY LUẬN...',
      latency: 'Độ trễ suy luận:',
      sentiment_class: 'PHÂN LỚP SENTIMENT',
      alpha_score: 'ĐIỂM ALPHA NHẤT QUÁN',
      recommendation: 'KHUYẾN NGHỊ HÀNH ĐỘNG',
      consistency_check: 'KIỂM ĐỊNH NHẤT QUÁN KOLMOGOROV',
      consistent: '✓ NHẤT QUÁN',
      violation: '⚠ ĐÃ CHIẾU ĐƠN THỂ (TCD)',
      thesis_title: 'Chuỗi Luận Điểm Tư Duy Kinh Tế (CoT Reasoning Thesis):',
      drift_title: 'Bảng Giám Sát Trôi Dạt Dự Báo & Rào Chắn Ngắt Mạch',
      window_info: 'Cửa sổ trượt: 30 phiên',
      dir_acc: 'ĐỘ CHÍNH XÁC ĐỊNH HƯỚNG (t+5)',
      spearman_ic: 'HỆ SỐ HẠNG SPEARMAN IC (t+5)',
      brier_score: 'ĐIỂM HIỆU CHUẨN BRIER SCORE',
      cb_state: 'TRẠNG THÁI RÀO CHẮN NGẮT MẠCH',
    },
    arena: {
      title: 'Đấu Trường 308 Bot Chiến Lược & Xưởng Thiết Kế AI Studio',
      subtitle: 'Mô phỏng vi cấu trúc Monte Carlo qua 5 kịch bản thị trường, vốn 10M VNĐ/bot, hỗ trợ khớp lệnh lô lẻ (Odd-lot 1-99) và phái sinh T+0',
      capital_badge: 'VỐN: 10,000,000 VNĐ / BOT',
      oddlot_badge: 'KHỚP LÔ LẺ (ODD-LOT 1-99)',
      total_bots_card: 'TỔNG SỐ BOT ĐẤU TRƯỜNG',
      ai_twins_desc: '154 Bản gốc quy tắc + 154 Phiên bản song sinh AI',
      initial_cash_card: 'VỐN KHỞI ĐIỂM QUY ĐỊNH',
      nav_cap_desc: 'Trần 25% NAV = 2,500,000 đ / vị thế',
      asset_class_card: 'LỚP TÀI SẢN CHO PHÉP',
      multi_asset_desc: 'Cổ phiếu, VN30F1M (T+0), Chứng quyền, ETF, Trái phiếu',
      pbo_card: 'XÁC SUẤT QUÁ TRÙNG KHỚP (PBO)',
      pbo_desc: 'Đạt ngưỡng an toàn theo chuẩn học thuật',
      leaderboard_title: 'Bảng Xếp Hạng Các Bot Quán Quân',
      filter_all: 'Tất cả',
      filter_ai: 'Song Sinh AI',
      filter_non_ai: 'Theo Quy Tắc',
      th_rank: 'Hạng',
      th_bot_id: 'Mã Bot',
      th_strategy: 'Chiến Lược Hợp Nhất',
      th_model: 'Phân Loại',
      th_sharpe: 'Mean Sharpe',
      th_return: 'Lợi Nhuận',
      th_maxdd: 'Max DD',
      th_winrate: 'Tỷ Lệ Thắng',
      studio_title: 'Xưởng Thiết Kế Chiến Lược AI Studio (CoT Reasoning + RAG Lakehouse)',
      slm_badge: 'TRÍ TUỆ NHÂN TẠO ĐỊNH LƯỢNG',
      welcome_msg: 'Chào bạn! Tôi là VESTA AI Quantitative Strategist. Tôi có thể giúp bạn phân tích thông tin cổ phiếu, truy vấn dữ liệu Lakehouse DuckDB và sinh cấu hình bot chiến lược. Hãy nhập mã cổ phiếu hoặc yêu cầu chiến lược của bạn!',
      reasoning_in_progress: 'VESTA Quant SLM đang suy luận chuỗi tư duy CoT và truy xuất RAG từ Lakehouse...',
      chat_placeholder: 'Nhập yêu cầu chiến lược (ví dụ: chiến lược đầu tư dài hạn) hoặc mã CP (ví dụ: cho tôi thông tin về VIC)...',
      generated_config: 'CẤU HÌNH BOT MỚI SINH',
      target_assets: 'Tài sản mục tiêu',
      signal_weights: 'Tỷ trọng tín hiệu',
      sharpe_forecast: 'Dự phóng Sharpe',
      rec_action: 'Khuyến nghị',
      dynamic_ranking_active: 'Bảng xếp hạng chiến lược tối ưu cho danh mục:',
      reset_overall_ranking: 'Bảng Tổng Thể (308 Bots)',
      ranking_source_note: 'Tự động tái xếp hạng dựa trên mô hình PhoBert-v2-base + FinDPO + HybridACD + VESTA SLM & Dữ liệu Lakehouse',
      th_action: 'Hành Động Khuyến Nghị',
    },
  },
  en: {
    nav: {
      overview: 'Overview',
      dashboard: 'Market Dashboard',
      crawler: 'Crawler Controller',
      preprocessing: 'QA Preprocessing',
      feedback: 'Model Feedback',
      arena: 'Bot Arena Studio',
      lang_btn: 'EN',
    },
    common: {
      healthy: 'SYSTEM OPERATIONAL',
      unhealthy: 'SYSTEM DISCONNECTED',
      loading: 'Loading data...',
      error: 'Error',
      search: 'Search symbol...',
      refresh: 'Refresh',
      close: 'Close',
      prev: 'Previous',
      next: 'Next',
      page: 'Page',
      of: 'of',
      all: 'All',
    },
    overview: {
      badge: 'NEXT-GENERATION AUTONOMOUS TRADING ARCHITECTURE',
      title: 'VESTA Multimodal Quantitative Research & Reasoning Platform',
      subtitle: 'End-to-end algorithmic trading system unifying DuckDB lakehouse pipelines, PhoBERT financial sentiment, Kolmogorov Simplex-TCD consistency gates, and 308-bot Monte Carlo arena simulations.',
      btn_dashboard: 'Open Market Dashboard',
      btn_arena: 'Explore Bot Arena',
      btn_crawler: 'Manage Data Crawlers',
      live_model_feed: 'Live Model Telemetry Stream',
      prod_badge: 'PRODUCTION RUNTIME',
      dir_acc: 'DIRECTION ACCURACY',
      peak_sharpe: 'PEAK SHARPE',
      latency: 'LATENCY',
      arch_title: 'VESTA Architecture Tiers',
      arch_subtitle: 'End-to-end pipeline from DuckDB lakehouse to AI deep models and algorithmic trading arena',
      status_badge: 'ALL MODULES OPERATIONAL',
      tiers: [
        {
          name: 'Lakehouse Ingestion',
          desc: '13 DuckDB modules: 1-minute and daily OHLCV bars, financial statements, accounting notes, news stream, VN30F futures, ETFs, and HNX bonds.',
          actionLabel: 'Open Crawler Controller →',
        },
        {
          name: 'Point-in-Time Preprocessing',
          desc: 'Look-ahead free point-in-time join pipeline, 11-dimensional data quality auditing, and major insider shareholder entity resolution.',
          actionLabel: 'View QA Pipeline →',
        },
        {
          name: 'Econometric Proof & Gating',
          desc: 'Symbol and month cluster bootstrap audits, Deflated Sharpe Ratio (DSR) and PBO testing, and 16-regime market state matrix.',
          actionLabel: 'View Market Regime Matrix →',
        },
        {
          name: 'Multimodal Modeling & Consistency',
          desc: 'Fine-tuned financial PhoBERT, Cross-Attention Multimodal Fusion, Kolmogorov Simplex-TCD projection gate, and Local SLM CoT reasoning.',
          actionLabel: 'Test Model Scoring Sandbox →',
        },
        {
          name: 'Real-Time Serving & Drift Control',
          desc: 'Sub-15ms low-latency streaming inference, SimHash wire news deduplication, rolling drift monitor, and fail-closed circuit breakers.',
          actionLabel: 'Inspect Drift Telemetry →',
        },
        {
          name: 'Multi-Bot Strategy Arena',
          desc: 'Tournament arena of 308 composite bots with 10M VND capital budget, odd-lot order support, 5 Monte Carlo market regimes, and AI Bot Studio.',
          actionLabel: 'Enter 308-Bot Arena →',
        },
      ],
    },
    dashboard: {
      title: 'Market Indices & Composite Trading Dashboard',
      subtitle: 'Real-time telemetry synchronized from DuckDB Lakehouse: VN-Index, VN30, HNX, UPCOM, and sector liquidity heatmaps.',
      live_badge: 'LIVE MARKET FEED',
      real_data: 'AUTHENTIC LAKEHOUSE DATA',
      advancing: 'Advancing',
      declining: 'Declining',
      unchanged: 'Unchanged',
      ceiling: 'Ceiling',
      floor: 'Floor',
      trading_val: 'Total Value',
      foreign_net: 'Foreign Net',
      heatmap_title: 'Market Liquidity & Sector Heatmap',
      by_val: 'By Traded Value',
      by_cap: 'By Market Cap',
      all_sectors: 'All Sectors',
      candlestick_title: 'Candlestick Technical Chart',
      search_ticker_placeholder: 'Search or enter ticker symbol (e.g. FPT, VIC, VCB)...',
      select_timeframe: 'Timeframe',
      foreign_flow_title: 'Foreign Institutional Net Flow (Past 20 Sessions)',
      corporate_events_title: 'Corporate Actions & Shareholder Meetings',
      financial_news_title: 'Real-Time Financial News Stream (Lakehouse vesta_news)',
      search_news_placeholder: 'Filter news by keyword or headline...',
      no_events: 'No corporate actions recorded in this window.',
      no_news: 'No matching news articles found.',
      loading_news: 'Loading financial news stream...',
      read_more: 'Read full article text ▼',
      collapse: 'Collapse article text ▲',
      date: 'Date',
      buy_bil: 'Buy (Bn)',
      sell_bil: 'Sell (Bn)',
      net_bil: 'Net (Bn)',
    },
    crawler: {
      title: 'Lakehouse Data Crawler & Ingestion Controller',
      subtitle: 'Automated data ingestion management replacing legacy desktop interfaces, featuring zero-lock buffer tables and atomic promotion',
      check_status: 'Check Lakehouse Status',
      atomic_ingest: 'Atomic Ingest to Core',
      config_title: 'Crawler Job Configuration',
      mode_latest: '1. Latest Delta Ingest',
      mode_category: '2. Category Pipeline',
      mode_all: '3. Full History Ingest',
      category_label: 'Target Subsystem:',
      scope_label: 'Symbol Scope:',
      scope_all: 'Full Market Universe (~1,820 tickers)',
      scope_vn30: 'VN30 Bluechips Basket (30 tickers)',
      scope_hose: 'HOSE Exchange (~400 tickers)',
      scope_hnx: 'HNX Exchange (~320 tickers)',
      delay_label: 'Request Delay & Max Pages:',
      buffer_label: 'Zero-Lock Buffer Ingestion',
      start_btn: 'START CRAWLER JOB',
      stop_btn: 'EMERGENCY STOP',
      lakehouse_status_title: 'Lakehouse DuckDB 13 Subsystems Status',
      th_category: 'Subsystem',
      th_records: 'Row Count',
      th_symbols: 'Tickers',
      th_date_range: 'Date Range',
      th_status: 'Health Status',
      terminal_title: 'Ingestion Console Terminal (SSE Live Stream)',
      auto_scroll: 'Auto-scroll',
      terminal_ready: '[Ready] No active crawler job running. Click "START CRAWLER JOB" to initiate ingestion...',
    },
    preprocessing: {
      title: 'Data Preprocessing & Econometric Verification',
      subtitle: 'Strict 0% look-ahead bias guarantee, 11-dimensional data quality auditing, and market regime classification matrix',
      dsr_badge: 'DSR = 0.942 (PASS)',
      pbo_badge: 'PBO = 4.8% (SAFE)',
      dag_title: 'Point-in-Time Preprocessing Data Flow (Pipeline DAG)',
      regime_title: '16 Market Regimes × 3 Exchanges Matrix',
      sign_flip_badge: 'SIGN-FLIP PHENOMENON ALERT',
      audit_desc: 'Microstructure audit rule: Detects periods where mean-reversion signals flip sign. During severe liquidity crunches, the system triggers a fail-closed gate to reject risky dip-buying orders.',
      th_regime_code: 'Regime ID',
      th_scenario: 'Market Scenario Name',
      th_hose: 'HOSE (Alpha)',
      th_hnx: 'HNX (Alpha)',
      th_upcom: 'UPCOM (Alpha)',
      th_sign_flip: 'Sign-Flip State',
      th_risk_rule: 'Risk Control Rule',
      sign_flip_alert: 'SIGN-FLIP NEGATIVE',
      normal_status: 'CANONICAL',
    },
    feedback: {
      title: 'Model Serving & Predictive Drift Monitoring',
      subtitle: 'Sub-15ms low-latency streaming inference, Kolmogorov Simplex-TCD projection gate, and Local SLM Chain-of-Thought reasoning',
      cb_badge: 'CIRCUIT BREAKER STATE',
      sandbox_title: 'Real-Time News Scoring Sandbox',
      sub15_badge: 'SUB-15MS LATENCY',
      input_label: 'Enter Vietnamese financial headline or pick a benchmark sample:',
      symbol_label: 'Symbol:',
      source_label: 'Source:',
      score_now: 'SCORE HEADLINE NOW',
      scoring: 'INFERRING...',
      latency: 'Inference Latency:',
      sentiment_class: 'SENTIMENT CLASS',
      alpha_score: 'CONSISTENT ALPHA SCORE',
      recommendation: 'RECOMMENDED ACTION',
      consistency_check: 'KOLMOGOROV CONSISTENCY GATE',
      consistent: '✓ CONSISTENT',
      violation: '⚠ TCD PROJECTED (VIOLATION)',
      thesis_title: 'Economic Reasoning Chain (CoT Thesis):',
      drift_title: 'Drift Telemetry & Automated Circuit Breaker Rail',
      window_info: 'Rolling Window: 30 sessions',
      dir_acc: 'DIRECTION ACCURACY (t+5)',
      spearman_ic: 'SPEARMAN RANK IC (t+5)',
      brier_score: 'BRIER CALIBRATION SCORE',
      cb_state: 'CIRCUIT BREAKER STATUS',
    },
    arena: {
      title: '308-Bot Tournament Arena & AI Strategy Studio',
      subtitle: 'Monte Carlo microstructure simulation across 5 market regimes, 10M VND budget per bot, odd-lot (1-99) support, and T+0 hedging',
      capital_badge: 'BUDGET: 10,000,000 VND / BOT',
      oddlot_badge: 'ODD-LOT COMPLIANT (1-99)',
      total_bots_card: 'TOTAL ARENA BOTS',
      ai_twins_desc: '154 Rule-based baselines + 154 AI Model Twins',
      initial_cash_card: 'MANDATORY CAPITAL BUDGET',
      nav_cap_desc: 'Max 25% NAV = 2,500,000 VND / position',
      asset_class_card: 'ELIGIBLE ASSET CLASSES',
      multi_asset_desc: 'Equities, VN30F1M (T+0), Warrants, ETFs, Bonds',
      pbo_card: 'PROBABILITY OF OVERFITTING',
      pbo_desc: 'Meets academic institutional safety thresholds',
      leaderboard_title: 'Top Champion Bots Leaderboard',
      filter_all: 'All Bots',
      filter_ai: 'AI Twins',
      filter_non_ai: 'Rule-Based',
      th_rank: 'Rank',
      th_bot_id: 'Bot ID',
      th_strategy: 'Composite Strategy',
      th_model: 'Type',
      th_sharpe: 'Mean Sharpe',
      th_return: 'Return',
      th_maxdd: 'Max DD',
      th_winrate: 'Win Rate',
      studio_title: 'AI Strategy Studio (CoT Reasoning + Lakehouse RAG)',
      slm_badge: 'QUANTITATIVE AI REASONING',
      welcome_msg: 'Hello! I am the VESTA AI Quantitative Strategist. I can analyze stock profiles, query DuckDB Lakehouse data and synthesize custom bot configurations optimized. Enter your investment idea or a ticker symbol!',
      reasoning_in_progress: 'VESTA Quant SLM is synthesizing Chain-of-Thought reasoning and retrieving Lakehouse RAG facts...',
      chat_placeholder: 'Enter strategy concept (e.g. defensive bot for VN30F1M) or ticker (e.g. give me info on VIC)...',
      generated_config: 'NEWLY GENERATED BOT CONFIG',
      target_assets: 'Target Assets',
      signal_weights: 'Signal Weights',
      sharpe_forecast: 'Projected Sharpe',
      rec_action: 'Recommendation',
      dynamic_ranking_active: 'Dynamic Strategy Leaderboard Tailored for:',
      reset_overall_ranking: 'Reset to Overall (308 Bots)',
      ranking_source_note: 'Automatically re-ranked based on F301+F302 + HybridACD + VESTA SLM & Lakehouse Data',
      th_action: 'Recommended Action',
    },
  },
};
