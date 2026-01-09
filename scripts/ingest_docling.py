import os
import sys
from docling.document_converter import DocumentConverter
from docling.chunking import HybridChunker
from qdrant_client.http import models

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.tools.vector_store import VectorStore
from src.config import settings

# --- CONFIGURATION ---
DATA_DIR = "data/raw_guidelines"

# Map filenames to their clinical condition
PDF_METADATA_MAP = {
    "Hypertension_WHO_split.pdf": "Hypertension",}
# PDF_METADATA_MAP = {
#     # Replace these with your actual filenames
#     "hypertension_guideline_2020.pdf": "Hypertension",
#     "ada_diabetes_standards_2025.pdf": "Diabetes",
#     "gold_copd_report_2025.pdf": "COPD"
# }

def create_payload_index(vector_store: VectorStore):
    """Creates an index on the 'condition' field for fast filtering."""
    print("Ensuring Payload Index exists for 'condition'...")
    try:
        vector_store.client.create_payload_index(
            collection_name=vector_store.collection_name,
            field_name="condition",
            field_schema=models.PayloadSchemaType.KEYWORD
        )
        print("✅ Payload index created/verified.")
    except Exception as e:
        print(f"Index creation note: {e}")

def process_and_ingest():
    print("Initializing Vector Store...")
    try:
        vector_store = VectorStore()
        # 1. Create Index
        create_payload_index(vector_store)
    except Exception as e:
        print(f"Failed to connect to Qdrant: {e}")
        return

    converter = DocumentConverter()
    
    # Iterate through defined PDFs
    for filename, condition in PDF_METADATA_MAP.items():
        file_path = os.path.join(DATA_DIR, filename)
        
        if not os.path.exists(file_path):
            print(f"⚠️  Skipping {filename}: File not found.")
            continue
            
        print(f"\n--- Processing {filename} ({condition}) ---")
        
        # 2. Convert PDF to Markdown
        print("   Converting PDF to Markdown...")
        result = converter.convert(file_path)
        doc = result.document
        markdown_text = doc.export_to_markdown()
        
        # 3. DEBUG: Save Markdown for review
        md_filename = filename.replace(".pdf", ".md")
        md_path = os.path.join(DATA_DIR, md_filename)
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(markdown_text)
        print(f"   📝 Saved debug markdown to: {md_filename}")
        
        # 4. Chunking
        print("   Chunking content...")
        chunker = HybridChunker(tokenizer="sentence-transformers/all-MiniLM-L6-v2")
        chunk_iter = chunker.chunk(doc)
        
        docs_to_ingest = []
        metadatas = []
        
        for i, chunk in enumerate(chunk_iter):
            text = chunk.text
            if len(text) < 50: continue
            headings = chunk.meta.headings or []
            # Metadata for filtering
            meta = {
                "source": filename,
                "condition": condition,
                "chunk_id": i,
                "type": "text" ,
                "content": text,
                "heading_1": headings[0] if len(headings) > 0 else "General",
                "heading_2": headings[1] if len(headings) > 1 else "",
                "heading_3": headings[2] if len(headings) > 2 else "",
                "all_headings": "; ".join(headings), # For keyword search
            }
            
            docs_to_ingest.append(text)
            metadatas.append(meta)
            
        # 5. Upsert
        if docs_to_ingest:
            print(f"   Ingesting {len(docs_to_ingest)} chunks into Qdrant...")
            vector_store.add_documents(docs_to_ingest, metadatas)
            print(f"   ✅ Successfully ingested {filename}")
        else:
            print("   ⚠️  No valid chunks found.")

if __name__ == "__main__":
    process_and_ingest()