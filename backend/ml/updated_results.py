import os
import json
import time
import warnings
import pandas as pd
from datetime import datetime, timedelta
from elasticsearch import Elasticsearch

warnings.filterwarnings("ignore")

# Importing ML modules
from sentiment_analysis import load_cryptobert, score_posts
from narrative_analysis import (
    run_topic_modelling,
    create_weekly_price_regimes,
    create_narrative_by_price_regime,
    create_narrative_by_volatility_regime,
    SELECTED_N_TOPICS
)

from price_analysis import (
    fetch_all_coin_prices,
    create_weekly_prices,
    detect_spikes,
    fetch_australian_news,
    calculate_correlations,
    TICKERS
)

# Note: I changed the import source
from scripts.updated_es_query import (
    query_new_posts,
    query_all_crypto_posts,
    load_checkpoint,
    save_checkpoint,
    COIN_KEYWORDS
)

# ES config
ES_URL = os.getenv("ES_URL") # value stored in yaml
ES_USER = os.getenv("ES_USER")
ES_PASSWORD = os.getenv("ES_PASSWORD")


START_DATE = "2016-10-06" # the date when mastodon was first released to public
END_DATE = datetime.now().strftime("%Y-%m-%d")

# Polling interval for continuous mode (default 300s)
POLL_INTERVAL_SECONDS = int(os.getenv("POLL_INTERVAL_SECONDS", "300"))

COIN_STOPWORDS = {
    "bitcoin": ["bitcoin", "bitcoins", "btc"],
    "ethereum": ["ethereum", "eth"],
    "bnb": ["bnb", "binance"],
    "xrp": ["xrp", "ripple"],
    "usdt": ["usdt", "tether"],
}

# Pushing the results back to ES.
def push_results_to_es(results, index="ml_results"):
    from elasticsearch.helpers import bulk

    try:
        es = Elasticsearch(ES_URL, basic_auth=(ES_USER, ES_PASSWORD), verify_certs=False)
        actions = [{"_index": index, "_source": result} for result in results]
        success, failed = bulk(es, actions, raise_on_error=False)
        print(f"Pushed {success}/{len(results)} results to ES")
        if failed:
            print(f"Failed documents: {len(failed)}")
    except Exception as e:
        print(f"ES push failed: {e}")

# Pre-event Sentiment
def get_pre_event_sentiment(daily_sentiment, event_date, days_before=3):
    """
    Calculating average sentiment in the 1-3 days before a spike event. Used a 3 day window to capture leading sentiment signals while avoiding same-day confounding where sentiment may react to rather than predict price movements.
    Returns: dict with avg sentiment, dominant label and narratives
    """
    event_dt = datetime.strptime(event_date, "%Y-%m-%d")
    pre_data = []

    for d in range(1, days_before + 1):
        check_date = (event_dt - timedelta(days=d)).strftime("%Y-%m-%d")
        match = daily_sentiment[daily_sentiment["date"] == check_date]

        if not match.empty:
            pre_data.append(match.iloc[0])

    if not pre_data:
        return {
            "avg_pre_sentiment": None,
            "pre_sentiment_label": "unavailable",
            "pre_topic": "unavailable",
            "days_available": 0
        }

    avg_sentiment = sum(r["avg_sentiment"] for r in pre_data) / len(pre_data)

    if avg_sentiment > 0.2:
        label = "Bullish"
    elif avg_sentiment < -0.2:
        label = "Bearish"
    else:
        label = "Neutral"

    # Most common topic in pre-event window
    topics = [r["dominant_topic"] for r in pre_data if "dominant_topic" in r]
    pre_topic = (max(set(topics), key=topics.count)if topics else "unavailable")

    return {
        "avg_pre_sentiment": round(float(avg_sentiment), 4),
        "pre_sentiment_label": label,
        "pre_topic": pre_topic,
        "days_available": len(pre_data)
    }

# Coin Analysis
def analyse_coin(coin, posts, price_df, tokenizer, model, text_field="text"):
    """
    Running a full analysis pipeline for a single coin. Scoring sentiment, discovering narratives and identifying spike events.
    Returns: dict with full analysis results for the coin
    """
    print(f"\n{'='*50}")
    print(f"Analysing {coin.upper()}")
    print(f"{'='*50}")

    coin_posts = [
        p for p in posts
        if any(
            kw in p.get(text_field, "").lower()
            for kw in COIN_KEYWORDS[coin]
        )
    ]

    if len(coin_posts) < 3:
        print(f"Not enough posts for {coin}")
        return None

    scored_posts = score_posts(coin_posts, tokenizer, model, text_field)

    if not scored_posts:
        print(f"No high-confidence posts for {coin}, skipping...")
        return None

    # NMF over hardcoded keywords - handles emerging narratives and scales with dataset size
    df = pd.DataFrame(scored_posts)
    df["date"] = pd.to_datetime(df["created_at"], format="mixed", utc=True).dt.strftime("%Y-%m-%d")
    df, topic_words = run_topic_modelling(
        df,
        SELECTED_N_TOPICS,
        COIN_STOPWORDS.get(coin, []),
        text_field
    )

    daily_sentiment = df.groupby("date").agg(
        avg_sentiment=("sentiment_score", "mean"),
        post_count=("sentiment_score", "count"),
        bullish_count=("sentiment_label", lambda x: (x == "Bullish").sum()),
        bearish_count=("sentiment_label", lambda x: (x == "Bearish").sum()),
        neutral_count=("sentiment_label", lambda x: (x == "Neutral").sum()),
        dominant_topic=("topic_label", lambda x: x.value_counts().index[0])
    ).reset_index()

    weekly_prices = create_weekly_prices(price_df)
    weekly_regimes = create_weekly_price_regimes(price_df)

    merged = pd.merge(
        daily_sentiment,
        price_df[["date", "Close", "daily_return", "week_start"]],
        on="date",
        how="inner"
    )

    # Correlation analysis
    weekly_merged = pd.merge(
        daily_sentiment.groupby(
            pd.to_datetime(
                daily_sentiment["date"]
            ).dt.to_period("W-SUN").astype(str)
        ).agg(
            avg_sentiment=("avg_sentiment", "mean"),
            post_count=("post_count", "sum")
        ).reset_index(),
        weekly_prices.assign(
            week=weekly_prices["week"].astype(str)
        ),
        left_on="date",
        right_on="week",
        how="inner"
    )

    correlations = (calculate_correlations(weekly_merged) if len(weekly_merged) > 2 else {})

    # Narrative by price regime
    merged_with_regime = pd.merge(
        df[["date", "topic_id", "topic_label", text_field]],
        pd.merge(
            price_df[["date", "week_start"]],
            weekly_regimes[
                [
                    "week_start",
                    "weekly_return_pct",
                    "price_regime",
                    "volatility_regime"
                ]
            ],
            on="week_start",
            how="left"
        ),
        on="date",
        how="left"
    )

    narrative_by_price = create_narrative_by_price_regime(merged_with_regime)
    narrative_by_volatility = create_narrative_by_volatility_regime(merged_with_regime)

    spikes = detect_spikes(price_df)
    spike_events = []

    cutoff_date = pd.to_datetime(datetime.now() - timedelta(days=30))

    for _, spike in spikes.iterrows():
        event_date = spike["date"]
        data_source = ("live_stream" if pd.to_datetime(event_date) >= cutoff_date else "backfill")

        # Pre-event sentiment
        pre_sentiment = get_pre_event_sentiment(daily_sentiment, event_date)

        # Australian news context
        news_context = fetch_australian_news(event_date)

        spike_events.append({
            "date": event_date,
            "coin": coin,
            "severity": spike["severity"],
            "direction": spike["direction"],
            "price_change": spike["price_change"],
            "close_price": round(float(spike["Close"]), 2),
            "pre_sentiment": pre_sentiment["pre_sentiment_label"],
            "avg_pre_sentiment": pre_sentiment["avg_pre_sentiment"],
            "dominant_topic": pre_sentiment["pre_topic"],
            "cause_category": news_context["cause_category"],
            "cause_weights": news_context["cause_weights"],
            "supporting_headlines": news_context["supporting_headlines"],
            "news_available": news_context["news_available"],
            "data_source": data_source
        })

    return {
        "coin": coin,
        "post_count": len(scored_posts),
        "overlap_days": len(merged),
        "correlations": correlations,
        "daily_sentiment": daily_sentiment.to_dict(orient="records"),
        "topic_words": topic_words.to_dict(orient="records"),
        "narrative_by_price_regime": (
            narrative_by_price.to_dict(orient="records")
        ),
        "narrative_by_volatility": (
            narrative_by_volatility.to_dict(orient="records")
        ),
        "spike_events": spike_events
    }

# Saves all analysis results to JSON files locally. Also pushes spike events to ES for visualization.
def save_results(all_results, output_dir="results"):
    os.makedirs(output_dir, exist_ok=True)

    all_spike_events = []
    all_daily_sentiment = []
    all_narratives = []
    all_correlations = []

    for coin, result in all_results.items():
        if not result:
            continue

        json.dump(
            result,
            open(f"{output_dir}/{coin}_results.json", "w"),
            indent=2,
            default=str
        )

        # Spike events
        for record in result.get("spike_events", []):
            all_spike_events.append(record)

        # Daily sentiment
        for record in result.get("daily_sentiment", []):
            record["coin"] = coin
            all_daily_sentiment.append(record)

        # Narratives
        for record in result.get("narrative_by_price_regime", []):
            record["coin"] = coin
            all_narratives.append(record)

        # Correlations
        all_correlations.append({
            "coin": coin,
            **result.get("correlations", {})
        })

    # Save spike events combined locally
    json.dump(
        all_spike_events,
        open(f"{output_dir}/spike_events.json", "w"),
        indent=2,
        default=str
    )

    # Push to 4 separate ES indices
    if all_spike_events:
        push_results_to_es(all_spike_events, index="ml_spike_events")
    if all_daily_sentiment:
        push_results_to_es(all_daily_sentiment, index="ml_daily_sentiment")
    if all_narratives:
        push_results_to_es(all_narratives, index="ml_narratives")
    if all_correlations:
        push_results_to_es(all_correlations, index="ml_correlations")

    print(f"\nResults saved to {output_dir}/")
    print(f"Spike events: {len(all_spike_events)}")
    print(f"Daily sentiment records: {len(all_daily_sentiment)}")
    print(f"Narrative records: {len(all_narratives)}")
    print(f"Correlation records: {len(all_correlations)}")


# MAIN PIPELINE - Runs the full ML pipeline for all coins.
def run_pipeline(mode="historical"):
    print(f"Starting pipeline | Mode: {mode}")

    print("\nLoading CryptoBERT...")
    tokenizer, model = load_cryptobert()

    while True:
        try:
            if mode == "streaming":
                # Load checkpoint cursor
                last_timestamp = load_checkpoint()
                print(
                    f"Polling ES from checkpoint: "
                    f"{last_timestamp}"
                )
                posts = query_new_posts(last_timestamp)
                # No new data
                if not posts:
                    print("No new posts found.")
                    time.sleep(POLL_INTERVAL_SECONDS)
                    continue
                text_field = "text"
            else:
                posts = query_all_crypto_posts()
                text_field = "text"

            print(f"Loaded {len(posts)} posts")

            latest_post = posts[-1]
            latest_timestamp = latest_post["created_at"]

            start_date = START_DATE
            end_date = datetime.now().strftime("%Y-%m-%d")

            print("Fetching price data...")
            all_prices = fetch_all_coin_prices(start_date, end_date)

            all_results = {}

            for coin in TICKERS:
                if coin not in all_prices:
                    continue

                if all_prices[coin].empty:
                    continue

                result = analyse_coin(coin, posts, all_prices[coin], tokenizer, model, text_field)

                if result:
                    all_results[coin] = result
                    
            save_results(all_results)

            if mode == "streaming":
                save_checkpoint(latest_timestamp)

                print(
                    f"Checkpoint advanced: "
                    f"{latest_timestamp}"
                )

            print("Pipeline cycle complete")

        except Exception as e:
            print(f"Pipeline failed: {e}")

        if mode != "streaming":
            break

        print(
            f"Sleeping {POLL_INTERVAL_SECONDS}s..."
        )
        time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode",
        default="historical",
        choices=["historical", "streaming"]
    )

    args = parser.parse_args()
    run_pipeline(mode=args.mode)