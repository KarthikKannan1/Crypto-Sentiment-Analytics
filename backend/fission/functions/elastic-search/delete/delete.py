from elasticsearch8 import Elasticsearch
from utils.config_util import get_es_url, get_es_username, get_es_password
from flask import request
import json
import logging

logger = logging.getLogger(__name__)
def main() -> str:
    try:
        index = request.headers.get("X-Fission-Params-Index")
        doc_id = request.headers.get("X-Fission-Params-Docid")

        if not index or not doc_id:
            raise ValueError("Missing required headers: X-Fission-Params-Index and X-Fission-Params-Docid")

        es_client = Elasticsearch(
            get_es_url(),
            verify_certs=False,
            ssl_show_warn=False,
            basic_auth=(get_es_username(), get_es_password())
        )

        result = es_client.delete(
            index=index,
            id=doc_id
        )

        return 'OK'

    except Exception as e:
        logger.error(f"Error deleting document: {e}")
        return f"Error deleting document: {e}"