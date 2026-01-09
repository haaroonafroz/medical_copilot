import os
import sys
from requests.exceptions import HTTPError

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.tools.vector_store import VectorStore

def load_and_ingest():
    print("Initializing Vector Store")
    try:
        vector_store = VectorStore()
    except HTTPError as e:
        print(f"Failed to connect to Qdrant: {e.response.text}")
        print("Ensure Qdrant collection exists and is named correctly")
        return

    # Simple loader for the sample markdown
    guideline_path = "data/raw_guidelines/sample_guideline.md"
    if not os.path.exists(guideline_path):
        print(f"File not found: {guideline_path}")
        return

    with open(guideline_path, "r", encoding="utf-8") as f:
        text = f.read()
    chunks = text.split("## ")
    
    docs = []
    metadatas = []
    
    for i, chunk in enumerate(chunks):
        if not chunk.strip():
            continue
        docs.append(f"## {chunk}") # Add header back
        metadatas.append({
            "source": "Hypertension_Guideline_2025.md",
            "content": f"## {chunk}",
            "chunk_id": i
        })

    print(f"Ingesting {len(docs)} chunks...")
    vector_store.add_documents(docs, metadatas)
    print("Ingestion complete.")

if __name__ == "__main__":
    load_and_ingest()

