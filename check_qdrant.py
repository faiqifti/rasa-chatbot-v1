import os
from dotenv import load_dotenv
from qdrant_client import QdrantClient

# Load environment variables from .env file
load_dotenv()

# Get credentials from environment variables
qdrant_url = os.getenv("QDRANT_URL")
qdrant_api_key = os.getenv("QDRANT_API_KEY")

# Check if variables are loaded
if not qdrant_url or not qdrant_api_key:
    print("❌ Error: QDRANT_URL or QDRANT_API_KEY not found in .env file.")
else:
    print("Connecting to Qdrant at:", qdrant_url)
    try:
        # Initialize the Qdrant client
        client = QdrantClient(
            url=qdrant_url, 
            api_key=qdrant_api_key
        )

        # A simple operation to check the connection: list all collections
        collections = client.get_collections()
        
        print("\n✅ Success! Connection to Qdrant is working.")
        print("Your collections:", collections)

    except Exception as e:
        print("\n❌ Failed to connect to Qdrant.")
        print("Error details:", e)