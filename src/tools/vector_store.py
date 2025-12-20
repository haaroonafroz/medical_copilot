from typing import List, Dict, Any, Optional
from qdrant_client import QdrantClient
from qdrant_client.http import models
from langchain_openai import OpenAIEmbeddings
from config import settings

class VectorStore:
    # Based on your medical-collection_info.json, the vector is named 'patient-labs'.
    # We must use this name for all operations.
    VECTOR_NAME = "patient-labs"

    def __init__(self):
        self.client = QdrantClient(url=settings.QDRANT_URL, api_key=settings.QDRANT_API_KEY)
        self.collection_name = settings.QDRANT_COLLECTION_NAME
        self.embeddings = OpenAIEmbeddings(api_key=settings.OPENAI_API_KEY)
        
        self._ensure_collection_exists()

    def _ensure_collection_exists(self):
        """Checks if collection exists; creates it if not (for local dev)."""
        if self.client.collection_exists(collection_name=self.collection_name):
            print(f"Connected to collection: {self.collection_name}")
            return

        print(f"Collection {self.collection_name} not found. Creating...")
        
        # Define vector config based on whether we use a named vector
        if self.VECTOR_NAME:
            vectors_config = {
                self.VECTOR_NAME: models.VectorParams(
                    size=1536,
                    distance=models.Distance.COSINE
                )
            }
        else:
            vectors_config = models.VectorParams(
                size=1536,
                distance=models.Distance.COSINE
            )

        self.client.create_collection(
            collection_name=self.collection_name,
            vectors_config=vectors_config
        )
        print(f"Created collection: {self.collection_name}")

    def add_documents(self, texts: List[str], metadatas: List[Dict[str, Any]]):
        """Embeds and indexes documents into Qdrant."""
        vectors = self.embeddings.embed_documents(texts)
        
        points = []
        for idx, (vector, meta) in enumerate(zip(vectors, metadatas)):
            # If using a named vector, the 'vector' field must be a dictionary
            vector_struct = {self.VECTOR_NAME: vector} if self.VECTOR_NAME else vector
            
            points.append(models.PointStruct(
                id=idx, 
                vector=vector_struct,
                payload=meta
            ))
        
        self.client.upsert(
            collection_name=self.collection_name,
            points=points
        )
        print(f"Upserted {len(points)} documents.")

    def search(self, query: str, limit: int = 3) -> List[Dict]:
        """Semantic search using the robust query_points API."""
        query_vector = self.embeddings.embed_query(query)
        
        # 'query_points' is the standard method in newer clients
        response = self.client.query_points(
            collection_name=self.collection_name,
            query=query_vector,
            using=self.VECTOR_NAME,
            limit=limit,
            with_payload=True
        )
        
        hits = getattr(response, "points", []) or getattr(response, "result", [])
        
        results = []
        for hit in hits:
            results.append({
                "content": hit.payload.get("content", ""),
                "source": hit.payload.get("source", "unknown"),
                "score": hit.score
            })
        return results