import os
import json
from elasticsearch import Elasticsearch

CHECKPOINT_FILE = "/app/checkpoints/checkpoint.json"


# Connecting to ES.  
ES_URL = os.getenv("ES_URL") # value stored in yaml
ES_USER = os.getenv("ES_USER")
ES_PASSWORD = os.getenv("ES_PASSWORD")
ES_INDEX = "processed-data"


# Matching Alexis' coin assignment.
COIN_KEYWORDS = {
    "bitcoin": ["bitcoin", "btc", "₿"],
    "ethereum": ["ethereum", "eth"],
    "bnb": ["bnb", "binance"],
    "xrp": ["xrp", "ripple"],
    "usdt": ["usdt", "tether"],
}


# Setting up and returning the ES client through a function. 
# Did not use top level approach of .es because if ES is down then only the query will fail and not the whole script. Meaning my model will receieve posts but they would be all posts.
def get_es_client():
    return Elasticsearch(
        ES_URL,
        basic_auth=(ES_USER, ES_PASSWORD),
        verify_certs=False
    )

# Filtering logic to extract the coins from the keywords mentioned above. Reference: https://www.elastic.co/docs/reference/query-languages/query-dsl/query-dsl-bool-query
def build_coin_should_clauses(coin=None):
    if coin:
        keywords = COIN_KEYWORDS[coin]
    else:
        keywords = [kw for values in COIN_KEYWORDS.values() for kw in values]
    
    return [{"match": {"text": kw}} for kw in keywords]

# load the flag from the file on persistent volume as the cursor 
def load_checkpoint():
    """
    Load the last processed timestamp checkpoint.
    """
    if not os.path.exists(CHECKPOINT_FILE):
        # Default starting point = 2016-10-06 (the date when mastodon was first released to public)
        return "2016-10-06T00:00:00.000Z"

    with open(CHECKPOINT_FILE, "r") as f:
        checkpoint = json.load(f)

    return checkpoint["created_at"]


# save the flag to the file on persistent volume as the cursor
def save_checkpoint(created_at):
    """
    Atomically save checkpoint to persistent storage.
    """
    temp_file = CHECKPOINT_FILE + ".tmp"

    checkpoint = {
        "created_at": created_at
    }

    with open(temp_file, "w") as f:
        json.dump(checkpoint, f)

    # Atomic replace prevents corruption during crashes
    os.replace(temp_file, CHECKPOINT_FILE)



def query_new_posts(last_timestamp, size=5000):
    """
    Query Elasticsearch for new posts after the checkpoint.
    Uses search_after for safe pagination and deterministic ordering.
    """
    es = get_es_client()

    query = {
        "bool": {
            "should": build_coin_should_clauses(),
            "minimum_should_match": 1
        }
    }

    body = {
        "query": query,
        "size": size,
        "sort": [
            {"created_at": "asc"},
        ],
        "search_after": [last_timestamp]
    }

    response = es.search(
        index=ES_INDEX,
        body=body
    )

    posts = []
    for hit in response["hits"]["hits"]:
        post = hit["_source"]
        posts.append(post)
        
    return posts


# The query function which queries all crypto related posts from ES. It covers all coins across all platforms and ingestion methods while acting as unified filter between ES and ML model.
def query_all_crypto_posts(size=10000):

    es = get_es_client()
    response = es.search(
        index=ES_INDEX,
        body={
            "query": {"bool": {"should": build_coin_should_clauses(), "minimum_should_match": 1}},
            "size": size,
            "sort": [{"created_at": {"order": "desc"}}]
        }
    )
    posts = [hit["_source"] for hit in response["hits"]["hits"]]
    print(f"Fetched {len(posts)} crypto posts from ES")
    return posts