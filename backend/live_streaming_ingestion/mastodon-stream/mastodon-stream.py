import asyncio
import json
import os
import httpx
from mastodon import Mastodon, StreamListener

# Configuration
INSTANCE_URL = 'https://mastodon.world' # mastodon.social keeps blocking me. 
MASTODON_WORLD_TOKEN = os.getenv("MASTODON_WORLD_TOKEN")
FISSION_URL = 'http://router.fission/enqueue/raw-mastodon'
BATCH_SIZE = 100
BATCH_TIMEOUT = 2.0

class BatchSender:
    def __init__(self, client):
        self.client = client
        self.queue = asyncio.Queue()
        
    async def add(self, data):
        """Non-blocking add to the internal queue."""
        await self.queue.put(data)
    
    async def worker(self):
        """Worker that manages batching and sending to Fission."""
        while True:
            batch = []
            start_time = asyncio.get_event_loop().time()

            while len(batch) < BATCH_SIZE:
                time_left = BATCH_TIMEOUT - (asyncio.get_event_loop().time() - start_time)
                if time_left <= 0:
                    break
                
                try:
                    item = await asyncio.wait_for(self.queue.get(), timeout=time_left)
                    batch.append(item)
                except asyncio.TimeoutError:
                    break

            if batch:
                await self.flush(batch)

    async def flush(self, batch_to_send):
        """Post the batch to the Fission router."""
        try:
            # batch_to_send is now a list of full raw dictionaries
            res = await self.client.post(FISSION_URL, json=batch_to_send, timeout=10)
            res.raise_for_status()
            print(f"Sent {len(batch_to_send)} raw Mastodon posts. Status: {res.status_code}")
        except Exception as e:
            print(f"Failed to send Mastodon batch: {e}")

class UnfilteredListener(StreamListener):
    def __init__(self, batch_sender, loop):
        self.batch_sender = batch_sender
        self.loop = loop

    def on_update(self, status):
        """
        Triggered only when a new post is created.
        """
        clean_status = json_serializable(status)
        if clean_status.get('language') == 'en':
            try:
                asyncio.run_coroutine_threadsafe(self.batch_sender.add(clean_status), self.loop)
            except Exception as e:
                print(f"Error passing status to queue: {e}", flush=True)

async def stream_mastodon():
    async with httpx.AsyncClient(timeout=30.0) as client:
        batch_sender = BatchSender(client)
        loop = asyncio.get_running_loop()
        
        # Start the background sender worker
        asyncio.create_task(batch_sender.worker())
        
        masto = Mastodon(access_token=MASTODON_WORLD_TOKEN, api_base_url=INSTANCE_URL)
        listener = UnfilteredListener(batch_sender, loop)

        print(f"Connecting to {INSTANCE_URL} ...")
        
        # run_async=True runs the stream listener in its own thread.
        handle = masto.stream_public(listener, run_async=True)
            
        # Brief wait to see if the background thread stays alive
        await asyncio.sleep(2)
        if not handle.is_alive():
            print("Error: Streaming connection failed immediately.")
            return

        print("Stream is now active.")

        while True:
            # Keep the main event loop alive for the worker task.
            await asyncio.sleep(1)


def json_serializable(obj):
    """Helper to convert Mastodon objects/datetimes to JSON-safe formats."""
    # Converts datetime objects to strings and dict-like objects to standard dicts
    return json.loads(json.dumps(obj, default=str))


if __name__ == "__main__":
    asyncio.run(stream_mastodon())
