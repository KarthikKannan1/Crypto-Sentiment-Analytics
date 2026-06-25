import os
import json
from flask import request
from elasticsearch8 import Elasticsearch
from elasticsearch8.helpers import scan

ES_URL = os.getenv("ES_URL", "https://elasticsearch-es-http.elastic.svc.cluster.local:9200")
ES_USER = os.getenv("ES_USER", "elastic")
ES_PASSWORD = os.getenv("ES_PASSWORD", "elastic")

ALLOWED_INDICES = {
    "ml_results",
    "ml_spike_events",
    "ml_daily_sentiment",
    "ml_narratives",
    "ml_correlations",
}

def main():
    es_client = Elasticsearch(
        ES_URL,
        verify_certs=False,
        ssl_show_warn=False,
        basic_auth=(ES_USER, ES_PASSWORD)
    )

    index = request.args.get("index", "ml_results")

    if index not in ALLOWED_INDICES:
        return json.dumps({
            "error": f"Index '{index}' is not allowed",
            "allowed_indices": sorted(list(ALLOWED_INDICES))
        })

    limit = int(request.args.get("limit", 200000))

    query = {
        "query": {
            "match_all": {}
        }
    }

    docs = scan(
        client=es_client,
        index=index,
        query=query,
        preserve_order=False
    )

    results = []
    for i, doc in enumerate(docs):
        if i >= limit:
            break
        results.append(doc["_source"])

    return json.dumps(results)