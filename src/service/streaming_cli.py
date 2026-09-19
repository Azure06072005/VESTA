"""src/service/streaming_cli.py

Command-line streaming interface for VESTA F401 Inference Service.
Allows piping real-time crawler JSON lines or running ad-hoc headline evaluations.

Usage:
  python -m service.streaming_cli --headline "FPT báo lãi kỷ lục quý 3" --source "CafeF"
  python -m service.streaming_cli --file "data/incoming_news.jsonl"
"""
from __future__ import annotations

import argparse
import json
import sys
import time

from service.inference_app import HeadlineScoreRequest, engine


def main():
    parser = argparse.ArgumentParser(description="VESTA Real-Time Streaming CLI")
    parser.add_argument("--headline", type=str, help="Single headline text to evaluate")
    parser.add_argument("--body", type=str, default=None, help="Article lead/body")
    parser.add_argument("--symbol", type=str, default=None, help="Ticker symbol (optional)")
    parser.add_argument("--source", type=str, default="CafeF", help="Source news outlet")
    parser.add_argument("--url", type=str, default=None, help="Article source URL")
    parser.add_argument("--file", type=str, default=None, help="Path to input JSON Lines file")

    args = parser.parse_args()

    if args.file:
        t0 = time.perf_counter()
        count = 0
        with open(args.file, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                data = json.loads(line)
                req = HeadlineScoreRequest(
                    headline=data.get("headline", ""),
                    body=data.get("body"),
                    symbol=data.get("symbol"),
                    source=data.get("source", args.source),
                    url=data.get("url") or data.get("source_url"),
                )
                res = engine.score_single(req)
                print(res.model_dump_json())
                count += 1
        elapsed = (time.perf_counter() - t0) * 1000.0
        print(f"\n[OK] Scored {count} articles in {elapsed:.2f} ms ({elapsed/count:.2f} ms/article)", file=sys.stderr)
    elif args.headline:
        req = HeadlineScoreRequest(
            headline=args.headline,
            body=args.body,
            symbol=args.symbol,
            source=args.source,
            url=args.url,
        )
        res = engine.score_single(req)
        print(json.dumps(res.model_dump(), indent=2, ensure_ascii=False))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
