import urllib.request
import urllib.parse
import http.cookiejar
import re
import json
import datetime as dt
import sys
import pandas as pd

sys.stdout.reconfigure(encoding='utf-8')

class VietstockEventsClient:
    def __init__(self):
        self.cj = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.cj))
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'vi,en-US;q=0.9,en;q=0.8',
        }
        self.token = None

    def ensure_token(self):
        if self.token:
            return self.token
        page_url = 'https://finance.vietstock.vn/lich-su-kien.htm'
        req = urllib.request.Request(page_url, headers=self.headers)
        with self.opener.open(req, timeout=12) as res:
            html = res.read().decode('utf-8', errors='ignore')
        match = re.search(r'name=[\"\']?__RequestVerificationToken[\"\']?[^>]*value=[\"\']?([^\s\"\'>]+)', html)
        if not match:
            raise RuntimeError("Could not extract __RequestVerificationToken from Vietstock page")
        self.token = match.group(1)
        return self.token

    def fetch_events(self, symbol: str, page_size: int = 100) -> list[dict]:
        token = self.ensure_token()
        api_url = 'https://finance.vietstock.vn/data/eventstypedata'
        post_headers = {
            'User-Agent': self.headers['User-Agent'],
            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'X-Requested-With': 'XMLHttpRequest',
            'Referer': 'https://finance.vietstock.vn/lich-su-kien.htm',
            'Origin': 'https://finance.vietstock.vn'
        }

        all_events = []
        # EventTypeID: 1 = Cổ tức / thưởng / phát hành; 5 = ĐHCĐ
        for event_type_id in [1, 5]:
            params = {
                'eventTypeID': str(event_type_id),
                'channelID': '0',
                'code': symbol.upper(),
                'catID': '-1',
                'fDate': '2010-01-01',
                'tDate': '2026-12-31',
                'page': '1',
                'pageSize': str(page_size),
                'orderBy': 'Date1',
                'orderDir': 'DESC',
                '__RequestVerificationToken': token
            }
            encoded = urllib.parse.urlencode(params).encode('utf-8')
            req = urllib.request.Request(api_url, data=encoded, headers=post_headers)
            try:
                with self.opener.open(req, timeout=12) as res:
                    raw_text = res.read().decode('utf-8-sig', errors='ignore')
                    parsed = json.loads(raw_text)
                    items = parsed[0] if isinstance(parsed, list) and len(parsed) > 0 and isinstance(parsed[0], list) else []
                    all_events.extend(items)
            except Exception as e:
                print(f"Warning fetching event_type_id={event_type_id} for {symbol}: {e}")

        return all_events

def parse_vietstock_date(val: object) -> dt.date | None:
    if not val or val == "null" or pd.isna(val):
        return None
    m = re.search(r"/Date\((\d+)\)/", str(val))
    if m:
        ts_ms = int(m.group(1))
        return dt.datetime.fromtimestamp(ts_ms / 1000, tz=dt.timezone.utc).date()
    try:
        return pd.to_datetime(val).date()
    except Exception:
        return None

def transform_events(raw_items: list[dict], symbol: str) -> pd.DataFrame:
    if not raw_items:
        return pd.DataFrame()

    rows = []
    seen_ids = set()

    for item in raw_items:
        event_id = str(item.get("EventID") or item.get("id") or "")
        if not event_id or event_id in seen_ids:
            continue
        seen_ids.add(event_id)

        name = str(item.get("Name") or "")
        note = str(item.get("Note") or "")
        title = str(item.get("Title") or "")
        channel_id = item.get("ChannelID")
        event_type_id = item.get("EventTypeID")

        # Map to closed set: DIVIDEND, MAJOR_SHAREHOLDER_TRADING, SHAREHOLDER_MEETING, OTHER
        if event_type_id == 5 or "đại hội" in name.lower() or "đhcđ" in title.lower():
            cat = "SHAREHOLDER_MEETING"
        elif channel_id in (13, 14, 15) or "cổ tức" in name.lower() or "thưởng" in name.lower():
            cat = "DIVIDEND"
        elif "nội bộ" in name.lower() or "cổ đông lớn" in name.lower() or "giao dịch" in name.lower():
            cat = "MAJOR_SHAREHOLDER_TRADING"
        else:
            cat = "OTHER"

        ex_date = parse_vietstock_date(item.get("GDKHQDate"))
        record_date = parse_vietstock_date(item.get("NDKCCDate"))
        payment_date = parse_vietstock_date(item.get("Time"))

        # Event date prioritized: ex_date -> record_date -> payment_date -> DateOrder
        event_date = ex_date or record_date or payment_date or parse_vietstock_date(item.get("DateOrder"))

        # Calculate payout_delay_days
        payout_delay_days = None
        if payment_date:
            anchor_date = ex_date or record_date
            if anchor_date and payment_date >= anchor_date:
                payout_delay_days = (payment_date - anchor_date).days

        # Extract cash amount from note (e.g. '1,000 đồng/CP')
        cash_amount = None
        match_cash = re.search(r'([\d\.,]+)\s*đồng/cp', note, re.I)
        if match_cash:
            try:
                cash_amount = float(match_cash.group(1).replace('.', '').replace(',', '.'))
            except Exception:
                pass

        rows.append({
            "symbol": symbol.upper(),
            "event_id": event_id,
            "event_type": cat,
            "event_date": event_date,
            "detail_json": json.dumps(item, default=str, ensure_ascii=False),
            "fetched_at": dt.datetime.now(dt.timezone.utc).replace(tzinfo=None),
            "payout_delay_days": payout_delay_days,
            "cash_dividend_amount": cash_amount,
            "ex_date": ex_date,
            "record_date": record_date,
            "payment_date": payment_date,
            "event_title": title,
            "note": note,
        })

    return pd.DataFrame(rows)

if __name__ == "__main__":
    client = VietstockEventsClient()
    for sym in ["FPT", "VNM"]:
        raw = client.fetch_events(sym)
        df = transform_events(raw, sym)
        print(f"=== {sym}: Extracted {len(df)} events ===")
        print(df[["event_id", "event_type", "event_date", "ex_date", "payment_date", "payout_delay_days", "cash_dividend_amount"]].head(6))
