import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

# Confidence threshold of 60% - filters out low confidence predictions that are essentially guesses
CONFIDENCE_THRESHOLD = 0.6 

# Loading CryptoBERT and tokenizer from HuggingFace. First run downloads the model (~500MB), subsequent runs use cache. Reference: https://huggingface.co/ElKulako/cryptobert
def load_cryptobert():

    print("Loading CryptoBERT...")
    tokenizer = AutoTokenizer.from_pretrained("ElKulako/cryptobert")
    model = AutoModelForSequenceClassification.from_pretrained("ElKulako/cryptobert")
    model.eval()
    print("CryptoBERT loaded!")
    return tokenizer, model

# Batch scoring - BERT handles multiple inputs at once, much faster than one at a time
def get_sentiment_batch(texts, tokenizer, model, batch_size=16):
    
    label_map = {0:"Bearish", 1:"Neutral", 2:"Bullish"}
    score_map = {0:-1, 1:0, 2:1}
    results = []

    for i in range(0, len(texts), batch_size):
        batch = texts[i:i+batch_size]
        inputs = tokenizer(
            batch,
            return_tensors="pt",
            truncation=True,
            max_length=512,
            padding=True
        )
        with torch.no_grad():
            outputs = model(**inputs)

        probs = torch.softmax(outputs.logits, dim=1)
        preds = probs.argmax(dim=1).tolist()
        confs = probs.max(dim=1).values.tolist()

        results += [
            {
                "label": label_map[p],
                "score": score_map[p],
                "confidence": round(c, 4)
            }
            for p, c in zip(preds, confs)
        ]
        
        if i % (batch_size * 10) == 0:
            print(f"Scored {min(i+batch_size, len(texts))}/{len(texts)}...")

    return results

# Score all posts and filter out anything below the confidence threshold
def score_posts(posts, tokenizer, model, text_field="text"):

    # Filtering empty posts
    valid = [p for p in posts if p.get(text_field, "").strip()]
    print(f"Valid posts: {len(valid)}/{len(posts)}")

    # Scoring in batches
    texts   = [p[text_field] for p in valid]
    results = get_sentiment_batch(texts, tokenizer, model)

    # Adding scores to posts
    for post, r in zip(valid, results):
        post.update({
            "sentiment_label": r["label"],
            "sentiment_score": r["score"],
            "confidence": r["confidence"]
        })

    # Confidence threshold on top of argmax - avoids false positives from uncertain predictions
    scored = [p for p in valid if p["confidence"] >= CONFIDENCE_THRESHOLD]
    print(f"High confidence posts: {len(scored)}/{len(valid)}")

    return scored

# For live streaming - scores one post at a time, returns None if empty or low confidence
def process_single_post(text, tokenizer, model):

    if not text.strip():
        return None

    result = get_sentiment_batch([text], tokenizer, model, batch_size=1)[0]

    if result["confidence"] < CONFIDENCE_THRESHOLD:
        return None

    return {
        "sentiment_label": result["label"],
        "sentiment_score": result["score"],
        "confidence": result["confidence"]
    }