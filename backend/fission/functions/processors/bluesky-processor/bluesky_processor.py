from utils.clean_and_format_util import clean_and_format
import json
import requests
import logging
from flask import request
from utils.config_util import get_enqueue_url
from utils.config_util import get_processed_data_topic
import sys
from typing import Optional

ingest_to_es_topic = get_processed_data_topic()
source = "bluesky"
logger = logging.getLogger(__name__)

def main() -> str:
    try:
        raw_data = request.get_data(as_text=True)
        raw_data_list = json.loads(raw_data.strip())

        processed_data_list = []
        for data_dict in raw_data_list:
                
            text = data_dict.get("record", {}).get("text", "")
            created_at = data_dict.get("record", {}).get("created_at", "")
            likes = data_dict.get("like_count", 0)
            comments = data_dict.get("reply_count", 0)
            shares = data_dict.get("repost_count", 0)

            commit = data_dict.get("commit", {})
            if data_dict.get("kind") == "commit" and commit.get("operation") == "create":
                text, created_at = from_stream(data_dict)

            processed_data = clean_and_format(text, created_at, source, likes, comments, shares)
            processed_data_list.append(processed_data)


        response: Optional[requests.Response] = requests.post(
            url=(get_enqueue_url() + ingest_to_es_topic),
            headers={'Content-Type': 'application/json'},
            json=processed_data_list
        )

        if response is not None and response.status_code != 200:
            raise Exception(f"Failed to enqueue processed data, status code: {response.status_code}, response: {response.text}")

        return 'OK'
    except Exception as e:
        logger.error(f"Error processing data: {str(e)}")
        return "ERROR: " + str(e)

def from_stream(data_dict: dict) -> str:
    text = data_dict.get("commit", {}).get("record", {}).get("text", "")
    created_at = data_dict.get("commit", {}).get("record", {}).get("createdAt", "")
    return text, created_at