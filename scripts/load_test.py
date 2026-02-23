import asyncio
import httpx
import time
import uuid

# Configuration
URL = "http://localhost:8000/health"
CONCURRENT_USERS = 500  # Max in-flight requests
TOTAL_REQUESTS = 2500   # Total requests to send

async def call_endpoint(client, user_id, semaphore):
    async with semaphore:
        try:
            # We use different user_id to avoid hitting the 15 req/min rate limit per user
            headers = {"X-User-ID": user_id} 
            start = time.perf_counter()
            resp = await client.get(URL, headers=headers)
            end = time.perf_counter()
            return resp.status_code, end - start
        except Exception as e:
            # Log the specific error for debugging
            # print(f"Error: {e}")
            return "ERROR", 0

async def run_load_test():
    print(f"🚀 Starting optimized load test: {CONCURRENT_USERS} concurrent users, {TOTAL_REQUESTS} total requests...")
    
    # Increase connection limits for the client
    limits = httpx.Limits(max_keepalive_connections=CONCURRENT_USERS, max_connections=CONCURRENT_USERS)
    timeout = httpx.Timeout(10.0, connect=5.0)
    
    semaphore = asyncio.Semaphore(CONCURRENT_USERS)

    async with httpx.AsyncClient(limits=limits, timeout=timeout) as client:
        tasks = []
        # Simulate different users
        user_ids = [str(uuid.uuid4()) for _ in range(TOTAL_REQUESTS)]
        
        for user_id in user_ids:
            tasks.append(call_endpoint(client, user_id, semaphore))

        start_time = time.perf_counter()
        results = await asyncio.gather(*tasks)
        end_time = time.perf_counter()

    # Process results
    total_time = end_time - start_time
    statuses = [r[0] for r in results]
    latencies = [r[1] for r in results if r[0] != "ERROR"]
    
    avg_latency = sum(latencies) / len(latencies) if latencies else 0
    throughput = len(results) / total_time

    print(f"\n--- Load Test Results ---")
    print(f"Total Time: {total_time:.2f} seconds")
    print(f"Throughput: {throughput:.2f} req/s")
    print(f"Avg Latency: {avg_latency*1000:.2f} ms")
    print(f"Success Count (200 OK): {statuses.count(200)}")
    print(f"Error Count: {statuses.count('ERROR')}")
    print(f"Rate limited (429): {statuses.count(429)}")

if __name__ == "__main__":
    asyncio.run(run_load_test())

