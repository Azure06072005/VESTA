import json
import os

with open('Harness/feature_list.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

COMMANDS_MAP = {
    "F000": {
        "run_command": "bash init.sh",
        "test_command": "pytest tests/test_db_bootstrap.py -v"
    },
    "F001": {
        "run_command": "python src/crawlers/dim_symbol.py",
        "test_command": "pytest tests/test_dim_symbol.py tests/test_dim_icb.py tests/test_symbol_exchange_history.py -v"
    },
    "F001b": {
        "run_command": "python src/crawlers/cafef_symbol_directory.py",
        "test_command": "pytest tests/test_cafef_symbol_directory.py -v"
    },
    "F001c": {
        "run_command": "python src/crawlers/dim_index_constituents.py",
        "test_command": "pytest tests/test_dim_index_constituents.py -v"
    },
    "F002": {
        "run_command": "python src/crawlers/market_ohlcv.py",
        "test_command": "pytest tests/test_market_crawler.py tests/test_price_adjustments.py -v"
    },
    "F002b": {
        "run_command": "python src/crawlers/intraday_ohlcv.py",
        "test_command": "pytest tests/test_intraday_ohlcv.py -v"
    },
    "F003": {
        "run_command": "python src/crawlers/vnstock_news.py",
        "test_command": "pytest tests/test_vnstock_news_crawler.py -v"
    },
    "F004": {
        "run_command": "python src/crawlers/cafef_news.py",
        "test_command": "pytest tests/test_cafef_crawler.py -v"
    },
    "F004b": {
        "run_command": "python src/crawlers/cafef_article_body.py",
        "test_command": "pytest tests/test_cafef_article_body.py -v"
    },
    "F004c": {
        "run_command": "python src/crawlers/cafef_category_news.py",
        "test_command": "pytest tests/test_cafef_category_news.py tests/test_cafef_category_orchestrator.py -v"
    },
    "F004d": {
        "run_command": "python src/pipeline/sector_news_matcher.py",
        "test_command": "pytest tests/test_sector_news_matcher.py -v"
    },
    "F005": {
        "run_command": "python src/crawlers/master_fundamentals_crawler.py",
        "test_command": "pytest tests/test_fundamental_crawler.py tests/test_fundamentals_source_fix.py -v"
    },
    "F006": {
        "run_command": "python src/crawlers/update_corporate_events.py",
        "test_command": "pytest tests/test_corporate_events.py -v"
    },
    "F007": {
        "run_command": "python src/crawlers/snapshots.py",
        "test_command": "pytest tests/test_snapshot_retention.py -v"
    },
    "F007b": {
        "run_command": "python src/crawlers/crawl_market_insights.py",
        "test_command": "pytest tests/test_market_insights.py -v"
    },
    "F050": {
        "run_command": "python src/crawlers/market_index_crawler.py",
        "test_command": "pytest tests/test_cafef_data_market.py -v"
    },
    "F051": {
        "run_command": "python src/crawlers/crawl_cafef_foreign_flow.py",
        "test_command": "pytest tests/test_cafef_foreign_flow.py -v"
    },
    "F052": {
        "run_command": "python src/crawlers/vietstock_finance_enhancer.py",
        "test_command": "pytest tests/test_cafef_finance_enhancer.py -v"
    },
    "F053": {
        "run_command": "python src/etl/batch_orchestrator.py",
        "test_command": "pytest tests/test_batch_orchestrator.py -v"
    },
    "F054": {
        "run_command": "python src/crawlers/vietstock_finance_enhancer.py",
        "test_command": "pytest tests/test_vietstock_finance_enhancer.py -v"
    },
    "F055": {
        "run_command": "python src/crawlers/vietstock_crawler.py",
        "test_command": "pytest tests/test_vietstock_crawler.py -v"
    },
    "F056": {
        "run_command": "python src/crawlers/worldbank_crawler.py",
        "test_command": "pytest tests/test_worldbank_crawler.py -v"
    },
    "F057": {
        "run_command": "python src/crawlers/sbv_crawler.py",
        "test_command": "pytest tests/test_sbv_crawler.py -v"
    },
    "F058": {
        "run_command": "python src/crawlers/nhandan_crawler.py",
        "test_command": "pytest tests/test_baochinhphu_crawler.py -v"
    },
    "F059": {
        "run_command": "python src/crawlers/ssc_crawler.py",
        "test_command": "pytest tests/test_ssc_crawler.py -v"
    },
    "F060": {
        "run_command": "python src/crawlers/vneconomy_crawler.py",
        "test_command": "pytest tests/test_vneconomy_crawler.py -v"
    },
    "F061": {
        "run_command": "python src/crawlers/tinnhanhchungkhoan_crawler.py",
        "test_command": "pytest tests/test_tinnhanhchungkhoan_crawler.py -v"
    },
    "F062": {
        "run_command": "python src/crawlers/thoibaotaichinh_crawler.py",
        "test_command": "pytest tests/test_new_sector_crawlers.py -v"
    },
    "F063": {
        "run_command": "python src/crawlers/thoibaonganhang_crawler.py",
        "test_command": "pytest tests/test_thoibaonganhang_crawler.py -v"
    },
    "F064": {
        "run_command": "python src/crawlers/vinaprint_crawler.py",
        "test_command": "pytest tests/test_vinaprint_crawler.py -v"
    },
    "F065": {
        "run_command": "python src/crawlers/vba_crawler.py",
        "test_command": "pytest tests/test_vba_crawler.py -v"
    },
    "F066": {
        "run_command": "python src/crawlers/nda_crawler.py",
        "test_command": "pytest tests/test_nda_crawler.py -v"
    },
    "F067": {
        "run_command": "python src/crawlers/hoinongdan_crawler.py",
        "test_command": "pytest tests/test_hoinongdan_crawler.py -v"
    },
    "F068": {
        "run_command": "python src/crawlers/moit_crawler.py",
        "test_command": "pytest tests/test_moit_crawler.py -v"
    },
    "F069": {
        "run_command": "python src/crawlers/vita_crawler.py",
        "test_command": "pytest tests/test_vita_crawler.py -v"
    },
    "F070": {
        "run_command": "python src/crawlers/vasep_crawler.py",
        "test_command": "pytest tests/test_vasep_crawler.py -v"
    },
    "F071": {
        "run_command": "python src/crawlers/horea_crawler.py",
        "test_command": "pytest tests/test_horea_crawler.py -v"
    },
    "F072": {
        "run_command": "python src/etl/merge_crawlers_staging.py",
        "test_command": "pytest tests/test_merge_crawlers_staging.py -v"
    },
    "F008": {
        "run_command": "python src/etl/retry_failed_jobs.py",
        "test_command": "pytest tests/test_retry_module.py -v"
    },
    "F009": {
        "run_command": "python src/etl/daily_crawler_orchestrator.py",
        "test_command": "pytest tests/test_data_integrity.py -v"
    },
    "F095": {
        "run_command": "python src/crawlers/market_index_crawler.py",
        "test_command": "pytest tests/test_market_index_crawler.py -v"
    },
    "F096": {
        "run_command": "python src/pipeline/clean_ohlcv_daily.py",
        "test_command": "pytest tests/test_ohlcv_cleaning.py -v"
    },
    "F097": {
        "run_command": "python src/pipeline/harmonize_intraday_1m.py",
        "test_command": "pytest tests/test_intraday_harmonization.py -v"
    },
    "F098": {
        "run_command": "python src/pipeline/dual_mode_adjustment.py",
        "test_command": "pytest tests/test_dual_mode_adjustment.py -v"
    },
    "F099": {
        "run_command": "python src/pipeline/ml/data_validation/eda.py --dataset ohlcv",
        "test_command": "pytest tests/test_data_quality_pipeline.py -k ohlcv -v"
    },
    "F099b": {
        "run_command": "python src/pipeline/ml/data_validation/eda.py --dataset news",
        "test_command": "pytest tests/test_news_dedup.py -v"
    },
    "F100": {
        "run_command": "python src/pipeline/ml/data_validation/eda.py --dataset fundamentals",
        "test_command": "pytest tests/test_financial_notes.py -v"
    },
    "F101": {
        "run_command": "python -m src.pipeline.validate_crossref --all",
        "test_command": "pytest tests/test_crossref_validation.py tests/test_tiered_validation.py -v"
    },
    "F102": {
        "run_command": "python -m src.pipeline.pit_join",
        "test_command": "pytest tests/test_pit_join.py -v"
    },
    "F103": {
        "run_command": "python -m src.pipeline.data_quality --profile",
        "test_command": "pytest tests/test_data_quality_pipeline.py -v"
    },
    "F104": {
        "run_command": "python -m src.pipeline.ml_features --export-split",
        "test_command": "pytest tests/test_ml_features.py tests/test_f104_dataset_split.py -v"
    },
    "F105": {
        "run_command": "python -m src.pipeline.news_fundamental_entity_matcher",
        "test_command": "pytest tests/test_news_fundamental_entity_matcher.py -v"
    },
    "F106": {
        "run_command": "python -m src.pipeline.cross_lakehouse_connector",
        "test_command": "pytest tests/test_cross_lakehouse_mapping.py -v"
    },
    "F201": {
        "run_command": "python -m src.pipeline.backtest_meanreversion --report out/meanreversion_report.json",
        "test_command": "pytest tests/test_meanreversion_stats.py -v"
    },
    "F202": {
        "run_command": "python -m src.pipeline.f201_robustness_check",
        "test_command": "pytest tests/test_f201_robustness.py -v"
    },
    "F202b": {
        "run_command": "python -m src.pipeline.f202b_dsr_pbo",
        "test_command": "pytest tests/test_f202b_dsr.py -v"
    },
    "F203": {
        "run_command": "python -m src.pipeline.f203_regime_audit --report out/f203_regime_report.json",
        "test_command": "pytest tests/test_f203_regime_audit.py -v"
    },
    "F301": {
        "run_command": "python -m src.models.train_sentiment --config configs/phobert_base.yaml",
        "test_command": "pytest tests/test_sentiment_eval.py tests/test_phobert_findpo.py -v"
    },
    "F302": {
        "run_command": "python -m src.models.train_multimodal_fusion --config configs/multimodal_fusion.yaml",
        "test_command": "pytest tests/test_multimodal_fusion.py -v"
    },
    "F303": {
        "run_command": "python -m src.pipeline.backtest_meanreversion --sentiment-source multimodal --report out/meanreversion_report_multimodal.json",
        "test_command": "pytest tests/test_f303_kelly_backtest.py tests/test_meanreversion_stats.py -v"
    },
    "F304": {
        "run_command": "python test_pipeline/f3xx_modeling/test_f304_hybridacd_runner.py",
        "test_command": "pytest tests/test_hybridacd_consistency_gate.py tests/test_hybridacd_10_checkers.py tests/test_self_supervised_adversarial.py -v"
    },
    "F305": {
        "run_command": "python test_pipeline/f3xx_modeling/test_f305_local_slm_runner.py",
        "test_command": "pytest tests/test_local_reasoning_slm.py -v"
    },
    "F401": {
        "run_command": "uvicorn src.service.inference_app:app --host 0.0.0.0 --port 8000",
        "test_command": "pytest tests/test_inference_service.py -v"
    },
    "F402": {
        "run_command": "python -m src.service.feedback_log --reconcile",
        "test_command": "pytest tests/test_feedback_log.py -v"
    },
    "F403": {
        "run_command": "python -m src.service.continuous_training --force-run",
        "test_command": "pytest tests/test_continuous_training.py -v"
    },
    "F501": {
        "run_command": "python -m src.pipeline.monte_carlo_bot_arena --paths 1000 --report out/f501_monte_carlo_arena_report.json",
        "test_command": "pytest tests/test_monte_carlo_arena.py -v"
    },
    "F901": {
        "run_command": "python scratch/compliance_broker_check.py",
        "test_command": "echo '[BLOCKED] Manual broker regulatory audit documentation only'"
    },
    "F902": {
        "run_command": "python src/execution/paper_trading_sandbox.py",
        "test_command": "pytest tests/test_execution_sandbox.py -v"
    }
}

updated_count = 0
for feat in data.get('features', []):
    fid = feat.get('id')
    if fid in COMMANDS_MAP:
        feat['run_command'] = COMMANDS_MAP[fid]['run_command']
        feat['test_command'] = COMMANDS_MAP[fid]['test_command']
        updated_count += 1
    else:
        print(f"WARNING: No command mapping for {fid}")

print(f"Updated {updated_count} / {len(data.get('features', []))} features.")

with open('Harness/feature_list.json', 'w', encoding='utf-8') as f:
    json.dump(data, f, indent=2, ensure_ascii=False)

print("Saved Harness/feature_list.json successfully!")
