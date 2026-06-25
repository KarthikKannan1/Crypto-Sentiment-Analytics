from typing import List, Dict, Any
from elasticsearch8 import Elasticsearch
from elasticsearch8.helpers import bulk
from utils.config_util import get_es_url, get_es_username, get_es_password
from flask import request
import json
import logging
import sys

#THIS INGEST IS FOR PROCESSED-DATA ONLY
#Cannot decouble due to mqtrigger, look in mqtrigger ingest spec for more details

elasticsearch_processed_data_index = "processed-data"
logger = logging.getLogger(__name__)
def main() -> str:

    raw_data = request.get_data(as_text=True)

    #Ingest always expects a list of json strings
    data : List[Dict[str, Any]] = json.loads(raw_data.strip())

    es_client: Elasticsearch = Elasticsearch(
        get_es_url(),
        verify_certs=False,
        ssl_show_warn=False,
        basic_auth=(get_es_username(), get_es_password())
    )
    
    bulk_payload = [ {"_index": elasticsearch_processed_data_index, "_source": d} for d in data ]

    success, errors = bulk(es_client, bulk_payload, raise_on_error=False)

    if errors:
        logger.error(errors)
        return "ERROR" + str(errors)

    return 'OK'
