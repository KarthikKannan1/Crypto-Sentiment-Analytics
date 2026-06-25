import html
import re
from bs4 import BeautifulSoup
from utils.engagement_calc_util import engagement_calc

def clean_and_format(text, created_at, source, likes, comments, shares):
    """
    Cleans text and calculates engagement score
    Returns formatted post dict for ElasticSearch
    """
    cleaned_text = clean_text(text)
    engagement = engagement_calc(likes, comments, shares)
    return {
        "text": cleaned_text,
        "created_at": created_at,
        "engagement": engagement,
        "source": source
    }

def clean_text(text):
    """
    Cleans raw social media text.
    Retains emojis for CryptoBERT sentiment analysis.
    """
    if not text:
        return ""
    text = html.unescape(text)
    text = BeautifulSoup(text, "html.parser").get_text()
    text = re.sub(r'http\S+|@\w+', '', text)
    text = re.sub(r'#(\w+)', r'\1', text)
    # Keep letters, numbers, spaces and emojis for CryptoBERT
    text = re.sub(r'[^a-zA-Z0-9\s\U00010000-\U0010ffff\u2600-\u27BF]', '', text)
    return re.sub(r'\s+', ' ', text).strip().lower()