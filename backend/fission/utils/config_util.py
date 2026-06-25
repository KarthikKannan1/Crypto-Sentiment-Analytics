import os

def config(k: str) -> str:
    with open(f'/configs/default/parameters/{k}', 'r') as f:
        return f.read().strip()

def get_es_url() -> str:
    return config("ES_URL")

def get_redis_host() -> str:
    return config("REDIS_HOST")

def get_enqueue_url() -> str:
    return config("ENQUEUE_URL")

def get_processed_data_topic() -> str:
    return config("PROCESSED_DATA_TOPIC")

def get_es_username() -> str:
    return os.getenv("ES_USERNAME")

def get_es_password() -> str:
    return os.getenv("ES_PASSWORD")