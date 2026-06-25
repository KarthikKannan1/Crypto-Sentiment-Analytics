import asyncio
import json
import websockets
import httpx

# Configuration
JETSTREAM_URL = "wss://jetstream2.us-east.bsky.network/subscribe?wantedCollections=app.bsky.feed.post"
FISSION_URL = 'http://router.fission/enqueue/raw-bluesky'
BATCH_SIZE = 100
BATCH_TIMEOUT = 2.0  # seconds

class BatchSender:
    def __init__(self, client):
        self.client = client
        self.queue = asyncio.Queue()  
        
    async def add(self, data):
        """Add data to the queue without blocking the main loop."""
        await self.queue.put(data)
    
    async def worker(self):
        """Background worker that handles batching and sending."""
        while True:
            batch = []
            start_time = asyncio.get_event_loop().time()

            # Fill batch until BATCH_SIZE is reached or BATCH_TIMEOUT expires
            while len(batch) < BATCH_SIZE:
                time_left = BATCH_TIMEOUT - (asyncio.get_event_loop().time() - start_time)
                
                if time_left <= 0:
                    break
                
                try:
                    # Wait for an item from the queue with a timeout
                    item = await asyncio.wait_for(self.queue.get(), timeout=time_left)
                    batch.append(item)
                except asyncio.TimeoutError:
                    break # Timeout reached, flush what we have

            if batch:
                await self.flush(batch)

    async def flush(self, batch_to_send):
        """Sends the batch to Fission with the required headers."""
        
        try:
            res = await self.client.post(
                FISSION_URL, 
                json=batch_to_send, 
                timeout=10
            )
            res.raise_for_status()
            
            if res.text == "OK":
                print(f"Sent {len(batch_to_send)} posts. Status: {res.status_code}")
            else:
                print(f"Warning: Fission returned {res.text}")
        except Exception as e:
            print(f"Failed to send batch: {e}")

async def stream_all_posts():
    # Increase timeout to handle network spikes
    async with httpx.AsyncClient(timeout=30.0) as client:
        batch_sender = BatchSender(client)
        
        # Start the background worker task
        worker_task = asyncio.create_task(batch_sender.worker())
        
        while True:
            try:
                print(f"Connecting to {JETSTREAM_URL}...")
                # ping_interval/timeout keeps the connection alive and detects dead sockets
                async with websockets.connect(
                    JETSTREAM_URL, 
                    ping_interval=20, 
                    ping_timeout=20
                ) as websocket:
                    print("Connection established.")
                    
                    while True:
                        message = await websocket.recv()
                        data = json.loads(message)
                        
                        commit = data.get("commit", {})
                        if data.get("kind") == "commit" and commit.get("operation") == "create":
                            record = commit.get("record", {})
                            # Filter for English posts
                            if "en" in record.get("langs", []):
                                await batch_sender.add(data)
                                
            except (websockets.ConnectionClosed, Exception) as e:
                print(f"Connection lost or error: {e}. Reconnecting in 5s...")
                await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(stream_all_posts())
    