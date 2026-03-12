import asyncio
from tcp.client import AsyncTCPClient

async def main():
    client = AsyncTCPClient("localhost", 3000, read_timeout=None)
    await client.start()

    # Send a message
    await client.send("Hello Server!")
    
    while True:
        # Wait for response
        response = await client.receive()
        print(f"Final Response: {response}")
        
        # Acknowledge processing
        client.acknowledge()
    
    await client.stop()

if __name__ == "__main__":
    asyncio.run(main())
