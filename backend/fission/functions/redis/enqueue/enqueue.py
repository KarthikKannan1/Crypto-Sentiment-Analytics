import redis
import json
import os
import logging
from flask import request
from utils.config_util import get_redis_host

logger = logging.getLogger(__name__)

def main() -> str:
    try:
        topic = request.headers["X-Fission-Params-Topic"]

        raw_data = request.get_data(as_text=True)

        if not topic:
            raise ValueError("Missing topic in request headers, please set X-Fission-Params-Topic header")

        json_data = json.loads(raw_data)

        redis_client = redis.StrictRedis(
            host=get_redis_host(),
            socket_connect_timeout=5,
            decode_responses=False
        )

        redis_client.lpush(
            topic,
            json.dumps(json_data).encode("utf-8")
        )

        return "OK"

    except Exception as e:
        logger.error(f"Error enqueuing data to Redis: {str(e)}")
        return "FAIL"

