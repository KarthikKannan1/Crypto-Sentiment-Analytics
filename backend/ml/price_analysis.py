import os
import requests
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta

TICKERS = {
    "bitcoin": "BTC-USD",
    "ethereum": "ETH-USD",
    "bnb": "BNB-USD",
    "xrp": "XRP-USD",
    "usdt": "USDT-USD",
}

# Spike detection thresholds based on daily returns
SIGNIFICANT_THRESHOLD  = 5.0  
CATASTROPHIC_THRESHOLD = 10.0 

# NewsAPI config so tha tonly Australian sources are taken into account.
NEWSAPI_KEY = os.getenv("NEWSAPI_KEY", "")
NEWSAPI_URL = "https://newsapi.org/v2/everything"
NEWSAPI_SOURCES = "abc-news-au,news-com-au,the-age,herald-sun"
NEWSAPI_DAYS = 30  # Free tier limit

# Event categorisation keywords
EVENT_CATEGORIES = {
    "political":    ["election","government","president","congress","senate",
                     "trump","biden","policy","vote","minister","albanese"],
    "economic":     ["fed","federal reserve","inflation","interest rate",
                     "recession","gdp","unemployment","dollar","rba",
                     "reserve bank","treasury"],
    "geopolitical": ["war","ukraine","russia","china","sanctions","conflict",
                     "military","nato","israel","iran","tariff"],
    "technical":    ["hack","exploit","upgrade","protocol","mainnet","fork",
                     "bug","security","breach","vulnerability"],
    "market":       ["etf","institutional","blackrock","whale","adoption",
                     "listing","exchange","sec","approval","asx","coinspot"],
    "pandemic":     ["covid","virus","pandemic","lockdown","health",
                     "who","outbreak","omicron"]
}

def fetch_coin_prices(coin, start_date, end_date):
    ticker = TICKERS.get(coin)
    if not ticker:
        print(f"Unknown coin: {coin}")
        return pd.DataFrame()

    print(f"Fetching {coin} prices ({start_date} to {end_date})...")
    df = yf.download(ticker, start=start_date, end=end_date, progress=False)

    # Flatten multi-level columns
    df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
    df["daily_return"] = df["Close"].pct_change() * 100
    df = df.dropna().reset_index()
    df["date"] = df["Date"].dt.strftime("%Y-%m-%d")
    df["coin"] = coin
    df["ticker"] = ticker
    df["week_start"] = (
        df["Date"]
        .dt.to_period("W-SUN")
        .apply(lambda x: x.start_time.date())
    )

    print(f"Fetched {len(df)} days of {coin} data")
    return df

def fetch_all_coin_prices(start_date, end_date):
    return {
        coin: fetch_coin_prices(coin, start_date, end_date)
        for coin in TICKERS
    }

def create_weekly_prices(daily_df):

    weekly = (
        daily_df.set_index("Date")
        .resample("W-MON")
        .agg({"Close": "last"})
        .reset_index()
    )

    weekly = weekly.rename(columns={"Date": "week"})
    weekly["weekly_return"] = weekly["Close"].pct_change() * 100
    weekly["weekly_volatility"] = weekly["weekly_return"].abs()

    return weekly.dropna()

# Detects price spikes based on daily returns, classifies by severity (significant/catastrophic) and direction (rally/crash)
def detect_spikes(daily_df):

    spikes = daily_df[abs(daily_df["daily_return"]) > SIGNIFICANT_THRESHOLD].copy()

    spikes["severity"] = spikes["daily_return"].apply(
        lambda x: "catastrophic" if abs(x) >= CATASTROPHIC_THRESHOLD
                  else "significant"
    )

    spikes["direction"] = spikes["daily_return"].apply(
        lambda x: "rally" if x > 0 else "crash"
    )

    spikes["price_change"] = spikes["daily_return"].apply(
        lambda x: f"+{x:.2f}%" if x > 0 else f"{x:.2f}%"
    )

    print(f"Found {len(spikes)} spikes "
          f"({len(spikes[spikes['severity']=='catastrophic'])} catastrophic, "
          f"{len(spikes[spikes['severity']=='significant'])} significant)")

    return spikes[["date","coin","Close","daily_return",
                   "severity","direction","price_change"]]

# Categorises spike events using Australian news headlines around the event date - keyword matching across political, economic, geopolitical, technical, market and pandemic categories
def categorise_event(headlines):

    scores = {cat: 0 for cat in EVENT_CATEGORIES}

    for headline in headlines:
        headline = headline.lower()
        for category, keywords in EVENT_CATEGORIES.items():
            scores[category] += sum(1 for kw in keywords if kw in headline)

    total = sum(scores.values())
    if total == 0:
        return "unknown", {}

    weights  = {cat: round(score/total * 100, 1)
                for cat, score in scores.items() if score > 0}
    dominant = max(scores, key=scores.get)

    return dominant, weights

# Fetches Australian news headlines for a given spike date and categorises the likely cause
def fetch_australian_news(event_date, api_key=NEWSAPI_KEY):
    
    # Check if within free tier range
    event_dt = datetime.strptime(event_date, "%Y-%m-%d")
    days_ago  = (datetime.now() - event_dt).days

    if days_ago > NEWSAPI_DAYS:
        return {
            "cause_category": "unavailable",
            "cause_weights": {},
            "supporting_headlines": [],
            "news_available": False,
            "reason": "NewsAPI free tier limit — historical news unavailable beyond 30 days"
        }

    if not api_key:
        return {
            "cause_category": "unavailable",
            "cause_weights": {},
            "supporting_headlines": [],
            "news_available": False,
            "reason": "NewsAPI key not configured"
        }

    try:
        response = requests.get(NEWSAPI_URL, params={
            "q": "bitcoin cryptocurrency crypto",
            "sources": NEWSAPI_SOURCES,
            "from": event_date,
            "to": (event_dt + timedelta(days=1)).strftime("%Y-%m-%d"),
            "language":"en",
            "sortBy": "publishedAt",
            "pageSize": 20,
            "apiKey": api_key
        }, timeout=10)

        articles = response.json().get("articles", [])

        if not articles:
            return {
                "cause_category": "no_news_found",
                "cause_weights": {},
                "supporting_headlines": [],
                "news_available": False,
                "reason": "No Australian news found for this date"
            }

        headlines = [a["title"] for a in articles if a.get("title")]
        dominant, weights = categorise_event(headlines)

        return {
            "cause_category": dominant,
            "cause_weights": weights,
            "supporting_headlines": headlines[:3],
            "news_available": True,
            "reason": None
        }

    except Exception as e:
        return {
            "cause_category": "unavailable",
            "cause_weights": {},
            "supporting_headlines": [],
            "news_available": False,
            "reason": str(e)
        }

def calculate_correlations(merged_df):

    merged_df = merged_df.copy()

    # next-week return column for lagged correlation analysis
    merged_df["next_week_return"] = merged_df["weekly_return"].shift(-1)

    # correlation analysis
    same_week_corr = merged_df["avg_sentiment"].corr(merged_df["weekly_return"])
    next_week_corr = merged_df["avg_sentiment"].corr(merged_df["next_week_return"])
    price_corr = merged_df["avg_sentiment"].corr(merged_df["Close"])
    postcount_corr = merged_df["post_count"].corr(merged_df["weekly_volatility"])

    print("Correlation results:")
    print(f"Sentiment vs same-week return: {same_week_corr:.4f}")
    print(f"Sentiment vs next-week return: {next_week_corr:.4f}")
    print(f"Sentiment vs price: {price_corr:.4f}")
    print(f"Post count vs volatility: {postcount_corr:.4f}")

    return {
        "sentiment_vs_same_week_return": round(float(same_week_corr), 4),
        "sentiment_vs_next_week_return": round(float(next_week_corr), 4),
        "sentiment_vs_price": round(float(price_corr), 4),
        "post_count_vs_volatility": round(float(postcount_corr), 4)
    }