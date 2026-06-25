import json
import time
import os
import requests 
from mastodon import Mastodon



MASTODON_SOCIAL_TOKEN = os.getenv("MASTODON_SOCIAL_TOKEN")
MASTODON_WORLD_TOKEN = os.getenv("MASTODON_WORLD_TOKEN")
MASTODON_CLOUD_TOKEN = os.getenv("MASTODON_CLOUD_TOKEN")
MASTODON_INFOSEC_TOKEN = os.getenv("MASTODON_INFOSEC_TOKEN")

COIN_ASSIGNMENTS = ["bitcoin", "ethereum", "bnb", "xrp", "usdt"]

# Crawling 4 big Mastodon instances, the other big instances either are temporarily closed for new applications
# or didn't approve my applications
MASTODON_TOKEN_INSTANCES = [(MASTODON_SOCIAL_TOKEN, "mastodon.social"),
                            (MASTODON_WORLD_TOKEN, "mastodon.world"),
                            (MASTODON_CLOUD_TOKEN, "mastodon.cloud"),
                            (MASTODON_INFOSEC_TOKEN, "infosec.exchange")]


def get_pod_assignment():
    # Get the pod number, default to 0
    pod_id = int(os.getenv("JOB_COMPLETION_INDEX", "0"))
    # Assign the coin based on the ID which is the index
    assigned_coin = COIN_ASSIGNMENTS[pod_id % len(COIN_ASSIGNMENTS)]
    
    return assigned_coin


def get_mastodon_posts(coin):
    
    for token, instance in MASTODON_TOKEN_INSTANCES:
        try:
            mastodon = Mastodon(access_token=token,
                                api_base_url=f'https://{instance}')
        except Exception as e:
            print(f"Authentication issue with {instance}: {e}")
            return

        current_max_id = None

        while True:
            try:
                # Fetch posts OLDER than current_max_id
                # Note: local=False gets posts from federated timelines, not just the local ones --> lots of duplicates
                posts = mastodon.timeline_hashtag(coin, local=False, max_id=current_max_id, limit=40)

                # If no posts are returned, then reached the end of history
                if not posts:
                    print(f"Finished crawling all history for {coin} from {instance}.")
                    break

                post_batch = []
                for post in posts:
                    # Only search for english posts
                    if post['language'] == 'en':
                        post_batch.append(json_serializable(post))

                
                if post_batch:
                    try:
                        requests.post(
                            url='http://router.fission/enqueue/raw-mastodon',
                            headers={'Content-Type': 'application/json'},
                            json=post_batch,
                            timeout=10
                        )
                        print(f"Sent batch of {len(post_batch)} posts to router for {coin} from {instance}.")

                    except Exception as e:
                        print(f"Error sending batch for {coin} from {instance}: {e}")
                    
                    
                    

                # Update the cursor to the oldest post in the batch to continue going back
                current_max_id = posts[-1]['id']
                
                # API limits = 300 requests / 5 min 
                time.sleep(2) 

            except Exception as e:
                print(f"Error: {e}")
                time.sleep(10) # Back off on error
        
        

def json_serializable(obj):
    """Helper to convert Mastodon objects/datetimes to JSON-safe formats."""
    return json.loads(json.dumps(obj, default=str))



if __name__ == "__main__":

    coin = get_pod_assignment()
    get_mastodon_posts(coin) 
    

        
