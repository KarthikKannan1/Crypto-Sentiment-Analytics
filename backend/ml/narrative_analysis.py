import numpy as np
import pandas as pd
from sklearn.decomposition import NMF
from sklearn.feature_extraction.text import TfidfVectorizer

# =========================
# SETTINGS
# =========================

# Use this one for the final analysis.
SELECTED_N_TOPICS = 4

# Price regime threshold:
# >= +3% weekly return = bull/increase
# <= -3% weekly return = bear/decrease
# otherwise = neutral/flat
WEEKLY_PRICE_THRESHOLD = 3.0

# Volatility spike threshold:
# >= +10% weekly return = high positive volatility
# <= -10% weekly return = high negative volatility
# otherwise = normal volatility
VOLATILITY_THRESHOLD = 10.0

# =========================
# TOPIC MODELLING
# =========================

def get_custom_stopwords(coin_stopwords):
    """
    Remove generic crypto words and noisy scraped metadata.
    """
    return list(TfidfVectorizer(stop_words="english").get_stop_words()) + coin_stopwords + [
        # generic crypto words
        "bitcoin",
        "bitcoins",
        "btc",
        "crypto",
        "cryptos",
        "cryptocurrency",
        "cryptocurrencies",
        "blockchain",
        "digitalassets",
        "coin",
        "coins",

        # noisy metadata / scraped tags
        "categorynews",
        "categorycryptocurrency",
        "categorymarkets",
        "categorymarketmovingexclusives",
        "cmswordpress",
        "pageisbzprobz",
        "symbolbtc",
        "symboldoge",
        "symboleth",
        "symbolsol",
        "symbolxrp",
        "symbolcoin",
        "tagcrypto",
        "tagdonaldtrump",
        "tagisraeliranconflict",
        "taganthonypompliano",
        "weexofficialwebsite",
        "weexexchange",
        "weexbitcoinprice",
        "weexofficial",
        "weexplatform",
        "weextrading",

        # generic words
        "says",
        "news",
        "market",
        "markets",
        "price",
        "prices",
        "week",
        "today"
    ]

def run_topic_modelling(df, n_topics, coin_stopwords, text_field="text"):
    """
    Run NMF topic modelling and assign each post to a discovered narrative. Modified to accept text_field parameter to support both ES ('text') and local JSON ('cleaned_post') inputs.
    """

    # Edge case handling: if there are too few posts, assign them all to a single "insufficient_data" topic to avoid errors and meaningless topics. This ensures the analysis can still run even if a coin has very little discussion.
    if len(df) < 2:
        df = df.copy()
        df["topic_id"] = 0
        df["topic_label"] = "insufficient_data"
        df["topic_strength"] = 0.0
        df["topic_probability"] = 0.0
        fallback_topic = pd.DataFrame([{
            "topic_id": 0,
            "topic_label": "insufficient_data",
            "top_words": []
        }])
        return df, fallback_topic

    texts = df[text_field].tolist()

    vectorizer = TfidfVectorizer(
        stop_words=get_custom_stopwords(coin_stopwords),
        max_features=1000,
        min_df=1,
        ngram_range=(1, 2)
    )

    X = vectorizer.fit_transform(texts)
    n_topics = min(n_topics, len(df))

    nmf_model = NMF(
        n_components=n_topics,
        random_state=42,
        init="nndsvda",
        max_iter=500
    )

    topic_matrix = nmf_model.fit_transform(X)

    df = df.copy()
    df["topic_id"] = topic_matrix.argmax(axis=1)

    topic_strength = topic_matrix.max(axis=1)
    total_strength = topic_matrix.sum(axis=1)

    df["topic_strength"] = topic_strength
    df["topic_probability"] = np.where(
        total_strength == 0,
        0,
        topic_strength / total_strength
    )

    feature_names = vectorizer.get_feature_names_out()
    topic_labels = {}
    topic_words_rows = []

    for topic_idx, topic in enumerate(nmf_model.components_):
        top_indices = topic.argsort()[-10:][::-1]
        top_words = [feature_names[i] for i in top_indices]
        label = ", ".join(top_words[:5])
        topic_labels[topic_idx] = label
        topic_words_rows.append({
            "topic_id": topic_idx,
            "topic_label": label,
            "top_words": top_words
        })

    df["topic_label"] = df["topic_id"].map(topic_labels)
    topic_words_df = pd.DataFrame(topic_words_rows)

    return df, topic_words_df


# =========================
# PRICE REGIME
# =========================

def classify_price_regime(x):
    """
    Classify weekly Bitcoin return into bull, bear, neutral, or unknown.
    """
    if pd.isna(x):
        return "unknown"
    elif x >= WEEKLY_PRICE_THRESHOLD:
        return "bull/increase"
    elif x <= -WEEKLY_PRICE_THRESHOLD:
        return "bear/decrease"
    else:
        return "neutral/flat"

def classify_volatility_regime(x):
    """
    Classify weekly return into volatility regimes.
    This keeps direction, so large increases and large decreases are separated.
    """
    if pd.isna(x):
        return "unknown"
    elif x >= VOLATILITY_THRESHOLD:
        return "high_positive_volatility"
    elif x <= -VOLATILITY_THRESHOLD:
        return "high_negative_volatility"
    else:
        return "normal_volatility"

def create_weekly_price_regimes(prices):
    """
    Convert daily prices into weekly regimes.
    """

    # Note: Modified to accept a dataframe directly instead of loading from file.

    weekly_prices = (
        prices.groupby("week_start", as_index=False)
        .agg(
            weekly_close=("Close", "last"),
            week_first_date=("date", "min"),
            week_last_date=("date", "max")
        )
    )

    weekly_prices["weekly_return_pct"] = (
        weekly_prices["weekly_close"].pct_change() * 100
    )

    weekly_prices["price_regime"] = weekly_prices["weekly_return_pct"].apply(
        classify_price_regime
    )

    weekly_prices["volatility_regime"] = weekly_prices["weekly_return_pct"].apply(
        classify_volatility_regime
    )

    return weekly_prices


# =========================
# TIME RANGE
# =========================

def active_date_range(group):
    """
    Get the first and last date where a narrative appears,
    plus how many days it was active.
    """
    dates = pd.to_datetime(group["date"])
    start_date = dates.min().date()
    end_date = dates.max().date()

    return pd.Series({
        "active_start_date": start_date,
        "active_end_date": end_date,
        "active_duration_days": (end_date - start_date).days + 1
    })


# =========================
# NARRATIVE DISTRIBUTION BY PRICE REGIME
# =========================

def create_narrative_by_price_regime(merged):
    """
    For each price regime, calculate narrative percentages.
    Example:
    During bull/increase weeks, what % of posts are each narrative?
    """
    summary = (
        merged.groupby(["price_regime", "topic_id", "topic_label"])
        .size()
        .reset_index(name="post_count")
    )

    summary["percentage_within_price_regime"] = (
        summary["post_count"]
        / summary.groupby("price_regime")["post_count"].transform("sum")
        * 100
    )

    ranges = (
        merged.groupby(["price_regime", "topic_id", "topic_label"])
        .apply(active_date_range)
        .reset_index()
    )

    summary = summary.merge(
        ranges,
        on=["price_regime", "topic_id", "topic_label"],
        how="left"
    )

    summary = summary.sort_values(
        ["price_regime", "percentage_within_price_regime"],
        ascending=[True, False]
    )

    return summary

def create_narrative_by_volatility_regime(merged):
    """
    For each volatility regime, calculate narrative percentages
    and include the actual weekly return range.
    """
    summary = (
        merged.groupby(["volatility_regime", "topic_id", "topic_label"])
        .agg(
            post_count=("topic_id", "count"),
            average_weekly_return_pct=("weekly_return_pct", "mean"),
            min_weekly_return_pct=("weekly_return_pct", "min"),
            max_weekly_return_pct=("weekly_return_pct", "max")
        )
        .reset_index()
    )

    summary["percentage_within_volatility_regime"] = (
        summary["post_count"]
        / summary.groupby("volatility_regime")["post_count"].transform("sum")
        * 100
    )

    ranges = (
        merged.groupby(["volatility_regime", "topic_id", "topic_label"])
        .apply(active_date_range)
        .reset_index()
    )

    summary = summary.merge(
        ranges,
        on=["volatility_regime", "topic_id", "topic_label"],
        how="left"
    )

    summary = summary.sort_values(
        ["volatility_regime", "percentage_within_volatility_regime"],
        ascending=[True, False]
    )

    return summary