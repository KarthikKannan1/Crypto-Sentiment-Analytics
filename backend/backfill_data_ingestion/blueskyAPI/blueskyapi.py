from datetime import datetime, timezone
from dateutil.relativedelta import relativedelta
from atproto import Client
import os 
import time
import requests 



USER_HANDLE = os.getenv("BLUESKY_USER_HANDLE")
APP_PASSWORD = os.getenv("BLUESKY_APP_PASSWORD")


# Get the pod number which gives the coin assignment for that pod 
COIN_ASSIGNMENTS = ["bitcoin", "ethereum", "bnb", "xrp", "usdt"]

def get_pod_assignment():
    # Get the pod number, default to 0
    pod_id = int(os.getenv("JOB_COMPLETION_INDEX", "0"))
    # Assign the coin based on the ID which is the index
    assigned_coin = COIN_ASSIGNMENTS[pod_id % len(COIN_ASSIGNMENTS)]
    
    return assigned_coin


# Generates monthly ISO-8601 time slices from a start date up to the current moment (which is April as of now)
# Bluesky was publicly launched in February 2024
def generate_time_slices(start_year=2024, start_month=2):
    time_slices = []
    # Initialize start date 
    current_slice_start = datetime(start_year, start_month, 1, tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)

    while current_slice_start < now:
        # get the start of the next month
        next_slice_start = current_slice_start + relativedelta(months=1)

        # format strings to ISO 8601 with the 'Z' suffix
        start_str = current_slice_start.strftime('%Y-%m-%dT%H:%M:%SZ')
        end_str = next_slice_start.strftime('%Y-%m-%dT%H:%M:%SZ')
        
        time_slices.append((start_str, end_str))
        
        current_slice_start = next_slice_start

    return time_slices



def get_bluesky_posts(coin, time_slices):
    client = Client()
    try:
        client.login(USER_HANDLE, APP_PASSWORD)
    except Exception as e:
        print(f"Authentication issue: {e}")
        return

    for start_date, end_date in time_slices:
        print(f"--- Fetching {coin} from {start_date} to {end_date} ---")
        cursor = None  # reset cursor for each time slice
        
        while True:
            try:
                params = {
                    'q': coin, 
                    'since': start_date, 
                    'until': end_date, 
                    'lang': 'en', 
                    'limit': 40, 
                    'cursor': cursor
                }
                
                response = client.app.bsky.feed.search_posts(params=params)
                post_batch = [post.model_dump() for post in response.posts]

                if post_batch:
                    # error handling for Fission router/Redis enqueue
                    try:
                        redis_res = requests.post(
                            url='http://router.fission/enqueue/raw-bluesky',
                            json=post_batch,
                            timeout=10
                        )
                        # check for status from the redis
                        redis_res.raise_for_status() 
                        print(f"Sent {len(post_batch)} posts. Status: {redis_res.status_code}")
                    except requests.exceptions.HTTPError as e:
                        print(f"Enqueue error ({redis_res.status_code}): {e}")
                       

                cursor = response.cursor
                if not cursor:
                    print(f"Finished time slice: {start_date} to {end_date}.")
                    break 

                time.sleep(1) # avoid rate limit (=3000 requests per 5 min), just to be safe

            except Exception as e:
                # If encounter bluesky 400 or 401 errors, skip the batch and move on to the next time slice
                print(f"Batch skipped: {start_date} to {end_date}. Bluesky API error: {e}")

                break


if __name__ == "__main__":
    coin = get_pod_assignment()
    time_slices = generate_time_slices()
    get_bluesky_posts(coin, time_slices)