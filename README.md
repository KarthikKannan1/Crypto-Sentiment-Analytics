# CryptoPulse: Real-Time Crypto Sentiment & Price Correlation Engine

A cloud-native big data pipeline that harvests cryptocurrency-related social media posts from **BlueSky** and **Mastodon**, scores sentiment using a domain-specific transformer model, discovers emerging narratives, and correlates public sentiment with real-world price movements across five major cryptocurrencies.

Originally built as a university group project (COMP90024 - Cluster and Cloud Computing, University of Melbourne), this repository contains my individual contribution: the **NLP and machine learning pipeline**, plus the overall system architecture.

> **Note:** This was a 5-person team project. My primary responsibility was the sentiment analysis, topic modelling, and price correlation pipeline (`backend/ml/`). Data harvesting (`backend/backfill_data_ingestion/`, `backend/live_streaming_ingestion/`), Fission/Kubernetes infrastructure (`backend/fission/`), and the frontend notebook were built by teammates as part of a collaborative cloud computing assignment.

---

## What it does

1. **Harvests** crypto-related posts from BlueSky and Mastodon, both historical backfill and live streaming
2. **Processes & cleans** raw posts via serverless Fission functions, storing them in ElasticSearch
3. **Scores sentiment** using [CryptoBERT](https://huggingface.co/ElKulako/cryptobert), a transformer model fine-tuned on crypto social media text
4. **Discovers narratives** using Non-negative Matrix Factorisation (NMF) topic modelling
5. **Detects price spikes** from live market data (via yfinance) and classifies them by severity and direction
6. **Contextualises spikes** with Australian news headlines (NewsAPI)
7. **Correlates** sentiment against price movement (same-week, next-week, lagged)
8. **Visualises** everything through a Jupyter Notebook frontend

## Architecture

```
Social Media APIs (BlueSky / Mastodon)
        │
        ▼
Backfill Crawlers + Live Streamers
        │
        ▼
Fission Functions (clean, format, enqueue via Redis)
        │
        ▼
ElasticSearch (processed-data index)
        │
        ▼
ML Pipeline (CryptoBERT → NMF → Price Correlation)
        │
        ▼
ElasticSearch (4 output indices: spike_events, daily_sentiment, narratives, correlations)
        │
        ▼
Jupyter Notebook Frontend
```

The entire system is deployed on Kubernetes, with serverless data processing handled by Fission and persistent storage/search handled by ElasticSearch.

## My contribution: the ML pipeline (`backend/ml/`)

| File | Purpose |
|---|---|
| `sentiment_analysis.py` | CryptoBERT sentiment scoring with confidence thresholding |
| `narrative_analysis.py` | NMF topic modelling + price/volatility regime classification |
| `price_analysis.py` | Price fetching, spike detection, Australian news context, correlation analysis |
| `updated_results.py` | Main pipeline orchestration, supports historical and continuous streaming modes |
| `scripts/updated_es_query.py` | ElasticSearch query layer with checkpoint-based pagination for streaming |

### Why CryptoBERT over VADER/TextBlob?

General-purpose sentiment models misclassify or ignore crypto-specific slang ("hodl", "rekt", "mooning"). CryptoBERT is fine-tuned specifically on crypto social media text, giving significantly more accurate sentiment classification for this domain.

### Why NMF over hardcoded keywords or LDA?

Hardcoded keyword classification requires constant manual maintenance and can't surface narratives that weren't anticipated in advance. NMF produces sparse, interpretable topics and scales efficiently as the corpus grows, well suited to an evolving, real-time social feed.

### Streaming architecture

The pipeline supports two modes:
- **Historical**: one-off batch processing of all available posts
- **Streaming**: continuous polling with a checkpoint system (atomic file writes to prevent corruption on crash) that tracks the last processed timestamp, enabling safe resumption without reprocessing data

## Tech stack

- **NLP/ML:** CryptoBERT (HuggingFace Transformers), scikit-learn (NMF, TF-IDF)
- **Data:** ElasticSearch, Redis, yfinance, NewsAPI
- **Infrastructure:** Kubernetes, Fission (serverless functions), Docker
- **Languages:** Python

## Limitations

- Sentiment models struggle with sarcasm, a known limitation of transformer-based sentiment classifiers on social media text
- NewsAPI's free tier limits historical news context to the past 30 days
- ElasticSearch query size limits constrain the volume of posts processed per batch in historical mode

## Running it

See [`backend/ml/`](./backend/ml/) for the ML pipeline specifically. Requires Python 3.11+, with dependencies managed via `uv` (see `pyproject.toml`).

```bash
cd backend/ml
uv sync
python updated_results.py --mode historical
```

Requires a running ElasticSearch instance with crypto-related posts indexed (see `database/mappings/` for index schemas).

## License

See [LICENSE](./LICENSE).
