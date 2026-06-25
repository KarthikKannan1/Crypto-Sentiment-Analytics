from typing import List, Dict, Any
from elasticsearch8 import Elasticsearch
from utils.config_util import get_es_url, get_es_username, get_es_password
from flask import request
import json
import logging

logger = logging.getLogger(__name__)
def main() -> str:

    index = request.headers["X-Fission-Params-Index"]

    query = request.get_data(as_text=True)
    query = json.loads(query)

    es_client: Elasticsearch = Elasticsearch(
        get_es_url(),
        verify_certs=False,
        ssl_show_warn=False,
        basic_auth=(get_es_username(), get_es_password())
    )
    
    try:
        results = es_client.search(
            index=index,
            body=query
        )
        return json.dumps(results.body)
    except Exception as e:
        logger.error(f"Error executing search query: {e}")
        return f"Error executing search query: {e}"

