import sys, os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from config import config
"""
Enhanced RAG Client with NVIDIA NIM Embeddings
Supports vector search using NVIDIA NIM API
"""
import os
import json
import hashlib
import numpy as np
from typing import List, Dict, Any, Optional
from pathlib import Path
import requests
import re
import base64
import time
import pickle
from research.web_search import WebSearchClient

try:
    import pdfplumber  # type: ignore
except Exception:
    pdfplumber = None

try:
    import fitz  # type: ignore
except Exception:
    fitz = None

try:
    from pypdf import PdfReader  # type: ignore
except Exception:
    PdfReader = None

try:
    import pytesseract  # type: ignore
except Exception:
    pytesseract = None

class NVIDIAEmbeddings:
    """NVIDIA NIM Embeddings API Client"""
    
    def __init__(self, api_key: str = None, model: str = None):
        """
        Initialize NVIDIA embeddings client.
        
        Args:
            api_key: NVIDIA API key (defaults to NVIDIA_API_KEY env var)
            model: Embedding model to use
        """
        self.api_key = api_key or os.getenv('NVIDIA_API_KEY')
        if not self.api_key:
            raise ValueError("NVIDIA_API_KEY not found in environment")
        
        if not self.api_key:
            raise ValueError("NVIDIA_API_KEY not found in environment")
        
        # STRICT NO-HARDCODING: Load from Env, default to config if needed (but prefer env)
        self.model = model or os.getenv("NVIDIA_EMBEDDING_MODEL")
        if not self.model:
             raise ValueError("NVIDIA_EMBEDDING_MODEL not found in .env")
        self.base_url = os.getenv("NVIDIA_BASE_URL", config.NVIDIA_BASE_URL)
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
    
    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for a list of texts.
        
        Args:
            texts: List of text strings to embed
            
        Returns:
            List of embedding vectors
        """
        url = f"{self.base_url}/embeddings"
        # Truncate each text block to 750 characters to prevent 400 Client Error (Token size limit)
        truncated_texts = [t[:750] for t in texts]
        payload = {
            "input": truncated_texts,
            "model": self.model,
            "input_type": "passage"
        }
        
        max_retries = 3
        backoff_factor = 2
        
        for attempt in range(max_retries):
            try:
                response = requests.post(url, json=payload, headers=self.headers, timeout=30)
                response.raise_for_status()
                
                data = response.json()
                embeddings = [item['embedding'] for item in data['data']]
                return embeddings
            
            except Exception as e:
                print(f"[EMBEDDINGS] Attempt {attempt+1}/{max_retries} failed: {e}")
                try:
                    # Print response details if available
                    if 'response' in locals() and response is not None:
                        print(f"[EMBEDDINGS] Server Response: {response.status_code} - {response.text}")
                except Exception:
                    pass
                if attempt == max_retries - 1:
                    print(f"[EMBEDDINGS] Error calling NVIDIA embeddings API after {max_retries} attempts. Falling back to zero embeddings.")
                    return [[0.0] * 1024 for _ in texts]
                
                sleep_time = backoff_factor ** attempt
                print(f"[EMBEDDINGS] Retrying in {sleep_time}s...")
                import time
                time.sleep(sleep_time)
    
    def embed_query(self, query: str) -> List[float]:
        """
        Generate embedding for a single query.
        
        Args:
            query: Search query string
            
        Returns:
            Embedding vector
        """
        url = f"{self.base_url}/embeddings"
        # Truncate query to 750 characters to prevent 400 Client Error (Token size limit)
        truncated_query = query[:750]
        payload = {
            "input": [truncated_query],
            "model": self.model,
            "input_type": "query"
        }
        
        max_retries = 3
        backoff_factor = 2
        
        for attempt in range(max_retries):
            try:
                response = requests.post(url, json=payload, headers=self.headers, timeout=30)
                response.raise_for_status()
                
                data = response.json()
                return data['data'][0]['embedding']
            
            except Exception as e:
                print(f"[EMBEDDINGS QUERY] Attempt {attempt+1}/{max_retries} failed: {e}")
                if attempt == max_retries - 1:
                    print(f"[EMBEDDINGS QUERY] Error embedding query after {max_retries} attempts. Falling back to zero vector.")
                    return [0.0] * 1024
                
                sleep_time = backoff_factor ** attempt
                print(f"[EMBEDDINGS QUERY] Retrying in {sleep_time}s...")
                import time
                time.sleep(sleep_time)


import faiss

class VectorStore:
    """FAISS-powered vector store for high-performance similarity search"""
    
    def __init__(self, storage_path: str = None):
        """Initialize vector store
        Args:
            storage_path: Path to save/load vector data. If None, defaults to data/vector_store.json
        """
        self.storage_path = storage_path or config.VECTOR_STORE_PATH
        self.index_path = self.storage_path.replace(".json", ".index")
        
        self.documents = []
        self.index = None
        self._load()
    
    def add_documents(self, documents: List[Dict[str, Any]], embeddings: List[List[float]]):
        """Add documents and their embeddings to the store"""
        if not embeddings:
            return

        # Convert to numpy float32
        embeddings_np = np.array(embeddings).astype('float32')
        faiss.normalize_L2(embeddings_np) # Normalize for Cosine Similarity (Inner Product)
        
        # Initialize index if needed
        if self.index is None:
            dimension = embeddings_np.shape[1]
            self.index = faiss.IndexFlatIP(dimension) # Inner Product for similarity
            
        self.index.add(embeddings_np)
        self.documents.extend(documents)
        self._save()
    
    def search(self, query_embedding: List[float], top_k: int = 5) -> List[Dict[str, Any]]:
        """
        Search for similar documents using FAISS.
        """
        if not self.index or self.index.ntotal == 0:
            return []
        
        # Convert to numpy float32
        query_vec = np.array([query_embedding]).astype('float32')
        faiss.normalize_L2(query_vec)
        
        # Search
        distances, indices = self.index.search(query_vec, top_k)
        
        results = []
        for i, idx in enumerate(indices[0]):
            if idx == -1 or idx >= len(self.documents):
                continue

            document = self.documents[idx]
            citation = document.get('citation', {})
            block_label = document.get('subtype') or document.get('type', 'document')
                
            results.append({
                "document": document,
                "score": float(distances[0][i]),
                "snippet": self._extract_snippet(document.get('content', '')),
                "block_type": block_label,
                "citation": citation,
            })
        
        return results
    
    def _extract_snippet(self, content: str, max_length: int = 200) -> str:
        """Extract snippet from content"""
        if len(content) <= max_length:
            return content
        return content[:max_length] + "..."
    
    def _save(self):
        """Save documents and FAISS index to disk"""
        # Save Documents (Metadata)
        os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)
        with open(self.storage_path, 'w', encoding='utf-8') as f:
            json.dump({"documents": self.documents}, f, ensure_ascii=False, indent=2)
            
        # Save FAISS index
        if self.index:
            faiss.write_index(self.index, self.index_path)
    
    def _load(self):
        """Load documents and FAISS index from disk"""
        # Load Documents
        if os.path.exists(self.storage_path):
            with open(self.storage_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self.documents = data.get('documents', [])
        
        # Load FAISS Index
        if os.path.exists(self.index_path):
            self.index = faiss.read_index(self.index_path)
        else:
            self.index = None


class EnhancedRAGClient:
    """
    Enhanced RAG client with NVIDIA NIM embeddings and vector search.
    Replaces the simpler keyword-based RAGClient.
    """
    
    def __init__(self, use_embeddings: bool = True, vector_store_path: str = None):
        """
        Initialize Enhanced RAG Client.
        
        Args:
            use_embeddings: If True, use NVIDIA embeddings. If False, fallback to keyword search.
            vector_store_path: Path to the vector store file (for Workspaces)
        """
        self.use_embeddings = use_embeddings
        
        if self.use_embeddings:
            try:
                self.embedder = NVIDIAEmbeddings()
                self.vector_store = VectorStore(storage_path=vector_store_path)
                print("[RAG] [OK] NVIDIA embeddings enabled")
            except ValueError as e:
                print(f"[RAG] [WARNING] {e}, falling back to keyword search")
                self.use_embeddings = False
        
        if not self.use_embeddings:
            from research.rag_client import RAGClient as SimpleRAG
            self.simple_rag = SimpleRAG()
            
        # Initialize Web Search
        self.web_search = WebSearchClient()
    
    def ingest_documents(self, file_paths: List[str]) -> Dict[str, Any]:
        """
        Ingest documents with embedding generation.
        Features dynamic fallback to Nemotron Ingest if available.
        
        Args:
            file_paths: List of document paths
            
        Returns:
            Ingestion status
        """
        # lazy import to avoid circular dependency or startup errors
        try:
            from research.nemotron_ingest import NemotronIngestor
            nemotron = NemotronIngestor()
        except ImportError:
            nemotron = None

        try:
            from research.youtube_loader import YouTubeLoader
            yt_loader = YouTubeLoader()
        except ImportError:
            yt_loader = None

        documents = []
        texts = []
        
        for path in file_paths:
            is_url = path.startswith("http://") or path.startswith("https://")
            if not is_url and not os.path.exists(path):
                print(f"[RAG] File not found: {path}")
                continue
            
            try:
                content = ""
                file_name = path
                
                # 1. Try YouTube / Video URL
                if is_url:
                    if yt_loader and yt_loader.available:
                        print(f"[RAG] 🎥 Processing video URL: {path}...")
                        result = yt_loader.load_and_process(path)
                        if result.get("status") == "success":
                            content = result.get("full_text", "")
                            file_name = result.get("title", path)
                            print(f"[RAG] ✅ Video extraction successful: {file_name}")
                        else:
                            print(f"[RAG] ⚠️ Video processing failed: {result.get('error')}")
                            continue
                    else:
                        print("[RAG] ⚠️ YouTubeLoader not available to process URL.")
                        continue

                # 2. Try Nemotron for PDFs
                elif nemotron and nemotron.available and path.lower().endswith(".pdf"):
                    print(f"[RAG] 🚀 Attempting Nemotron Ingest for {os.path.basename(path)}...")
                    result = nemotron.ingest_file(path)
                    
                    if result.get("status") == "success":
                        content = result.get("full_text", "")
                        file_name = os.path.basename(path)
                        print(f"[RAG] ✅ Nemotron extraction successful ({len(result.get('tables', []))} tables found)")
                    else:
                        print(f"[RAG] ⚠️ Nemotron failed ({result.get('error')}), falling back to standard read")

                # 2b. Layout-aware PDF fallback: preserve text, tables, and images as separate blocks.
                is_multimodal_pdf = False
                if not content and path.lower().endswith(".pdf"):
                    pdf_result = self._ingest_pdf_multimodal(path)
                    if pdf_result.get("status") == "success":
                        content = pdf_result.get("full_text", "")
                        file_name = os.path.basename(path)
                        is_multimodal_pdf = True
                        
                        # Fix the original bug: append structured blocks to outer documents & texts scopes
                        for block in pdf_result.get("documents", []):
                            doc = {
                                "type": "pdf_block",
                                "subtype": block.get("subtype"),
                                "file_path": block.get("file_path"),
                                "file_name": block.get("file_name"),
                                "chunk_id": len(documents),
                                "content": block.get("content", ""),
                                "page_number": block.get("page_number"),
                                "order": block.get("order"),
                                "caption": block.get("caption"),
                                "image_b64": block.get("image_b64"),
                                "metadata": block.get("metadata", {}),
                                "citation": block.get("citation", {}),
                                "timestamp": block.get("timestamp")
                            }
                            documents.append(doc)
                            texts.append(block.get("content", "") or block.get("caption", ""))
                        
                        if pdf_result.get("citations"):
                            print(f"[RAG] 📎 PDF citations preserved for {len(pdf_result.get('citations', []))} blocks")
                        print(
                            f"[RAG] ✅ PDF multimodal extraction successful: "
                            f"{pdf_result.get('table_count', 0)} tables, {pdf_result.get('image_count', 0)} images"
                        )
                    else:
                        print(f"[RAG] ⚠️ PDF multimodal extraction failed ({pdf_result.get('error')})")
                
                # 3. Standard Read Fallback for local files
                if not content and not is_url:
                    file_name = os.path.basename(path)
                    with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()
                
                if not content:
                    continue
                
                # Extract and save document metadata schema for PDFs
                if path.lower().endswith(".pdf") and content:
                    try:
                        meta_data = self._extract_document_metadata(path, content)
                        self._save_document_metadata(path, meta_data)
                    except Exception as me:
                        print(f"[RAG] ⚠️ Metadata extraction skipped/failed: {me}")
                    
                # Only chunk the text if it was not already processed as multimodal blocks
                if not is_multimodal_pdf:
                    chunk_size = int(os.getenv("RAG_CHUNK_SIZE", "512"))
                    chunk_overlap = int(os.getenv("RAG_CHUNK_OVERLAP", "128"))
                    chunks = self._chunk_text(content, chunk_size=chunk_size, overlap=chunk_overlap)
                    
                    for i, chunk in enumerate(chunks):
                        doc = {
                            "type": "research_document" if not is_url else "video_transcript",
                            "file_path": path,
                            "file_name": file_name,
                            "chunk_id": len(documents),
                            "content": chunk,
                            "timestamp": time.time()
                        }
                        documents.append(doc)
                        texts.append(chunk)
            
            except Exception as e:
                print(f"[RAG] Error ingesting {path}: {e}")
        
        if not documents:
            return {"status": "error", "message": "No documents ingested"}
        
        # Generate embeddings if enabled
        if self.use_embeddings:
            print(f"[RAG] Generating embeddings for {len(texts)} chunks...")
            embeddings = self.embedder.embed_texts(texts)
            self.vector_store.add_documents(documents, embeddings)
            print(f"[RAG] ✅ Ingested {len(documents)} chunks with embeddings")
        else:
            # Use simple RAG fallback
            return self.simple_rag.ingest_documents(file_paths)
        
        return {
            "status": "success",
            "ingested": len(file_paths),
            "chunks": len(documents)
        }

    def _clean_text(self, text: str) -> str:
        """Pembersihan visual filler seperti titik berturut-turut untuk menghemat token."""
        text = re.sub(r'\.{2,}', ' ', text)
        text = re.sub(r'[-_]{2,}', ' ', text)
        text = re.sub(r'\s+', ' ', text)
        return text.strip()

    def _ingest_pdf_multimodal(self, pdf_path: str) -> Dict[str, Any]:
        """Extract PDF text, tables, and images into structured blocks with layout-awareness.

        This keeps page order and separates layout elements so the retriever can
        preserve context even if the PDF layout is messy.
        """
        if not os.path.exists(pdf_path):
            return {"status": "error", "error": f"File not found: {pdf_path}"}

        blocks: List[Dict[str, Any]] = []
        full_text_parts: List[str] = []
        citations: List[Dict[str, Any]] = []
        table_count = 0
        image_count = 0
        ocr_count = 0
        source_name = os.path.basename(pdf_path)

        # Open documents if packages are available
        fitz_doc = None
        pdf_doc = None
        num_pages = 0
        
        try:
            if fitz is not None:
                fitz_doc = fitz.open(pdf_path)
                num_pages = len(fitz_doc)
            if pdfplumber is not None:
                pdf_doc = pdfplumber.open(pdf_path)
                num_pages = max(num_pages, len(pdf_doc.pages))
        except Exception as e:
            print(f"[RAG] Error opening PDF {pdf_path}: {e}")
            
        if num_pages > 0:
            for page_index in range(1, num_pages + 1):
                # A. Extract Text first
                text = ""
                if fitz_doc is not None and page_index <= len(fitz_doc):
                    try:
                        page = fitz_doc[page_index - 1]
                        blocks_list = page.get_text("blocks")
                        if blocks_list:
                            width = page.rect.width
                            mid = width / 2
                            has_left = any(b[0] < mid and b[2] <= mid + 20 for b in blocks_list if len(b[4].strip()) > 5)
                            has_right = any(b[0] >= mid - 20 and b[2] > mid for b in blocks_list if len(b[4].strip()) > 5)
                            
                            if has_left and has_right:
                                # 2-column layout column sorting
                                def get_block_key(b):
                                    x0, y0, x1, y1, txt, block_no, block_type = b
                                    if x0 < mid - 20 and x1 > mid + 20:
                                        col = 0
                                    elif x0 < mid:
                                        col = 1
                                    else:
                                        col = 2
                                    return (col, y0)
                                sorted_blocks = sorted(blocks_list, key=get_block_key)
                            else:
                                sorted_blocks = sorted(blocks_list, key=lambda x: x[1])
                            
                            text = "\n".join(b[4].strip() for b in sorted_blocks if b[4].strip())
                        text = self._clean_text(text)
                    except Exception as e:
                        print(f"[RAG] fitz text extraction failed on page {page_index}: {e}")

                source_label = "fitz_layout_aware"
                
                # Fallback to pdfplumber for text if fitz failed or returned empty
                if not text and pdf_doc is not None and page_index <= len(pdf_doc.pages):
                    try:
                        page = pdf_doc.pages[page_index - 1]
                        text = (page.extract_text(x_tolerance=2, y_tolerance=2) or "").strip()
                        text = self._clean_text(text)
                        source_label = "pdfplumber_text"
                    except Exception as e:
                        print(f"[RAG] pdfplumber text extraction failed on page {page_index}: {e}")

                if text:
                    blocks.append({
                        "subtype": "text",
                        "page_number": page_index,
                        "order": 0,
                        "content": text,
                        "metadata": {"source": source_label},
                    })
                    citations.append({"page": page_index, "block_type": "text", "order": 0})
                    full_text_parts.append(f"[TEXT p{page_index}]\n{text}\n")

                # B. OCR Fallback if text is still empty
                if pytesseract is not None and not text and pdf_doc is not None and page_index <= len(pdf_doc.pages):
                    try:
                        page = pdf_doc.pages[page_index - 1]
                        page_image = page.to_image(resolution=200).original
                        ocr_text = self._normalize_ocr_text(pytesseract.image_to_string(page_image) or "")
                        ocr_text = self._clean_text(ocr_text)
                        if ocr_text:
                            ocr_count += 1
                            blocks.append({
                                "subtype": "ocr_text",
                                "page_number": page_index,
                                "order": 1,
                                "content": ocr_text,
                                "metadata": {"source": "pytesseract_ocr"},
                            })
                            citations.append({"page": page_index, "block_type": "ocr_text", "order": 1})
                            full_text_parts.append(f"[OCR p{page_index}]\n{ocr_text}\n")
                    except Exception as exc:
                        print(f"[RAG] OCR failed on page {page_index}: {exc}")

                # C. Extract Images of this page (using fitz)
                if fitz_doc is not None and page_index <= len(fitz_doc):
                    try:
                        page = fitz_doc[page_index - 1]
                        images = page.get_images(full=True)
                        for image_index, image in enumerate(images, start=1):
                            xref = image[0]
                            base_image = fitz_doc.extract_image(xref)
                            image_bytes = base_image.get("image", b"")
                            if not image_bytes:
                                continue
                            image_count += 1
                            image_b64 = base64.b64encode(image_bytes).decode("utf-8")
                            caption = base_image.get("ext", "image")
                            blocks.append({
                                "subtype": "image",
                                "page_number": page_index,
                                "order": image_index,
                                "content": caption,
                                "caption": caption,
                                "image_b64": image_b64,
                                "metadata": {
                                    "source": "pymupdf_image",
                                    "width": base_image.get("width"),
                                    "height": base_image.get("height"),
                                },
                            })
                            citations.append({"page": page_index, "block_type": "image", "order": image_index})
                            full_text_parts.append(f"[IMAGE p{page_index} #{image_index}] {caption}\n")
                    except Exception:
                        pass

                # D. Extract Tables of this page (using pdfplumber)
                if pdf_doc is not None and page_index <= len(pdf_doc.pages):
                    try:
                        page = pdf_doc.pages[page_index - 1]
                        tables = page.extract_tables() or []
                        for table_index, table in enumerate(tables, start=1):
                            markdown_table = self._table_to_markdown(table)
                            if markdown_table.strip():
                                table_count += 1
                                blocks.append({
                                    "subtype": "table",
                                    "page_number": page_index,
                                    "order": table_index,
                                    "content": markdown_table,
                                    "metadata": {"source": "pdfplumber_table"},
                                })
                                citations.append({"page": page_index, "block_type": "table", "order": table_index})
                                full_text_parts.append(f"[TABLE p{page_index} #{table_index}]\n{markdown_table}\n")
                    except Exception as exc:
                        print(f"[RAG] pdfplumber table extraction failed on page {page_index}: {exc}")
            
            # Close docs
            try:
                if fitz_doc is not None:
                    fitz_doc.close()
                if pdf_doc is not None:
                    pdf_doc.close()
            except Exception:
                pass

        # 3. pypdf fallback if fitz and pdfplumber both failed to find blocks
        if not blocks and PdfReader is not None:
            try:
                reader = PdfReader(pdf_path)
                for page_index, page in enumerate(reader.pages, start=1):
                    text = (page.extract_text() or "").strip()
                    text = self._clean_text(text)
                    if text:
                        blocks.append({
                            "subtype": "text",
                            "page_number": page_index,
                            "order": 0,
                            "content": text,
                            "metadata": {"source": "pypdf_text"},
                        })
                        citations.append({"page": page_index, "block_type": "text", "order": 0})
                        full_text_parts.append(f"[TEXT p{page_index}]\n{text}\n")
            except Exception as exc:
                print(f"[RAG] pypdf fallback failed: {exc}")

        if not blocks:
            return {"status": "error", "error": "No content extracted from PDF"}

        # Format block coordinates and citation metadata
        for block in blocks:
            block["file_path"] = pdf_path
            block["file_name"] = source_name
            block["timestamp"] = time.time()
            block["citation"] = {
                "page": block.get("page_number"),
                "block_type": block.get("subtype"),
                "order": block.get("order"),
                "source": source_name,
            }

        return {
            "status": "success",
            "file_path": pdf_path,
            "file_name": source_name,
            "summary": self._summarize_pdf_blocks(blocks),
            "full_text": "\n".join(full_text_parts),
            "documents": blocks,
            "citations": citations,
            "table_count": table_count,
            "image_count": image_count,
            "ocr_count": ocr_count,
        }

    def _extract_document_metadata(self, file_path: str, full_content: str) -> Dict[str, Any]:
        """Klasifikasi tipe dokumen dan ekstraksi metadata terstruktur berbasis tipe."""
        file_name = os.path.basename(file_path)
        print(f"[RAG] 🔍 Extracting metadata schema for: {file_name}...")
        
        # Ambil halaman pertama / teks awal (misal 3000 karakter pertama) untuk cover page analysis
        cover_text = full_content[:3000]
        
        # Buat prompt terperinci untuk LLM
        prompt = f"""Tugas: Analisis teks halaman sampul (cover page) dokumen akademik berikut untuk menentukan tipenya, lalu ekstrak metadata terstruktur yang sesuai.

TEKS SAMPUL DOKUMEN:
{cover_text}

ATURAN KLASIFIKASI & SCHEMA METADATA:
Tentukan tipe dokumen sebagai salah satu dari: "Tugas Akhir", "Skripsi", "Jurnal", "Pedoman/Peraturan", atau "Lainnya".

Sesuai tipe dokumen yang dipilih, isi bidang-bidang metadata berikut:

1. Tipe "Tugas Akhir":
   - judul: Judul Lengkap Tugas Akhir
   - penulis: Nama Lengkap Mahasiswa
   - nim: NIM Mahasiswa (Nomor Induk Mahasiswa)
   - pembimbing: Daftar Nama Dosen Pembimbing
   - program_studi: Program Studi / Jurusan
   - tahun: Tahun Lulus / Sidang
   - lembaga: Nama Universitas / Lembaga (contoh: Politeknik STMI Jakarta)
   - tempat_penelitian: Nama perusahaan tempat penelitian / magang jika ada (contoh: PT SKF Indonesia)

2. Tipe "Skripsi":
   - judul: Judul Lengkap Skripsi
   - penulis: Nama Lengkap Mahasiswa
   - nim: NIM Mahasiswa
   - pembimbing: Daftar Nama Dosen Pembimbing
   - program_studi: Program Studi / Jurusan
   - tahun: Tahun Sidang
   - lembaga: Nama Universitas / Institut
   - tempat_penelitian: Perusahaan tempat penelitian jika ada

3. Tipe "Jurnal":
   - judul: Judul Jurnal / Artikel Ilmiah
   - penulis: Daftar nama penulis (authors)
   - nama_jurnal: Nama jurnal penerbit jika tercantum
   - volume: Volume jurnal
   - nomor: Nomor edisi jurnal
   - halaman: Rentang halaman
   - tahun: Tahun publikasi
   - doi: DOI string/link jika ada
   - abstrak: Ringkasan singkat abstrak
   - kata_kunci: Kata kunci (keywords)
   - afiliasi: Universitas atau lembaga asal penulis

4. Tipe "Pedoman/Peraturan":
   - judul: Nama Pedoman / Peraturan (contoh: Pedoman Tugas Akhir)
   - nomor_keputusan: Nomor keputusan Direktur / SK jika ada (contoh: 444/BPSDMI/STMI/KEP/V/2021)
   - penerbit: Lembaga penerbit (contoh: Direktur Politeknik STMI Jakarta)
   - tahun: Tahun penetapan peraturan
   - tim_penyusun: Daftar nama tim penyusun/pengarah

5. Tipe "Lainnya":
   - judul: Judul dokumen
   - penulis: Penulis
   - tahun: Tahun dokumen
   - ringkasan: Ringkasan singkat isi

Format Output yang DIWAJIBKAN:
Kembalikan HANYA objek JSON dengan format persis seperti di bawah ini tanpa penjelasan tambahan atau block markdown:
{{
  "doc_type": "<salah satu tipe di atas>",
  "metadata": {{
     // masukkan bidang-bidang schema yang sesuai di sini
  }}
}}
"""
        try:
            from teacher import Teacher
            teacher = Teacher(model_type="reasoning")
            response = teacher.ask(
                prompt,
                system_instruction="You are an expert document metadata classifier. You output ONLY raw JSON."
            )
            
            response = response.strip()
            if response.startswith("```json"):
                response = response.replace("```json", "").replace("```", "")
            elif response.startswith("```"):
                response = response.replace("```", "")
            response = response.strip()
            
            meta_json = json.loads(response)
            print(f"[RAG] ✅ Metadata extracted: Tipe = {meta_json.get('doc_type')}")
            return meta_json
            
        except Exception as e:
            print(f"[RAG] ⚠️ Metadata extraction failed: {e}")
            return {
                "doc_type": "Lainnya",
                "metadata": {
                    "judul": file_name,
                    "penulis": "Tidak diketahui",
                    "tahun": "Tidak diketahui"
                }
            }

    def _save_document_metadata(self, file_path: str, meta_data: Dict[str, Any]):
        """Menyimpan metadata dokumen ke file metadata_store.json dalam folder workspace."""
        file_name = os.path.basename(file_path)
        store_path = Path(self.vector_store.storage_path).parent / "metadata_store.json"
        
        existing_data = {}
        if store_path.exists():
            try:
                with open(store_path, "r", encoding="utf-8") as f:
                    existing_data = json.load(f)
            except Exception as e:
                print(f"[RAG] ⚠️ Error loading existing metadata store: {e}")
                
        existing_data[file_name] = {
            "file_path": file_path,
            "doc_type": meta_data.get("doc_type", "Lainnya"),
            "metadata": meta_data.get("metadata", {}),
            "updated_at": time.time()
        }
        
        try:
            store_path.parent.mkdir(parents=True, exist_ok=True)
            with open(store_path, "w", encoding="utf-8") as f:
                json.dump(existing_data, f, ensure_ascii=False, indent=2)
            print(f"[RAG] 💾 Metadata stored in workspace database: {store_path.name}")
        except Exception as e:
            print(f"[RAG] ⚠️ Error saving metadata store: {e}")

    def _normalize_ocr_text(self, text: str) -> str:
        """Normalize OCR output so broken scans are still usable."""
        lines = [line.strip() for line in text.splitlines()]
        cleaned = [line for line in lines if line]
        return "\n".join(cleaned).strip()

    def _summarize_pdf_blocks(self, blocks: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Return a compact summary of extracted PDF block types."""
        summary = {"text": 0, "ocr_text": 0, "table": 0, "image": 0}
        for block in blocks:
            subtype = block.get("subtype", "")
            if subtype in summary:
                summary[subtype] += 1
        return summary

    def _table_to_markdown(self, table: Any) -> str:
        if not table:
            return ""

        rows = []
        for row in table:
            if not row:
                continue
            rows.append([str(cell).strip() if cell is not None else "" for cell in row])

        if not rows:
            return ""

        header = rows[0]
        body = rows[1:] if len(rows) > 1 else []

        def render(row: List[str]) -> str:
            return "| " + " | ".join(cell.replace("\n", " ") for cell in row) + " |"

        lines = [render(header), render(["---"] * len(header))]
        for row in body:
            if len(row) < len(header):
                row = row + [""] * (len(header) - len(row))
            lines.append(render(row[: len(header)]))
        return "\n".join(lines)
    
    def search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """
        Search documents using vector similarity.
        
        Args:
            query: Search query
            top_k: Number of results
            
        Returns:
            List of relevant documents
        """
        # Load workspace metadata database and build a pseudo-document result
        meta_results = []
        try:
            store_path = Path(self.vector_store.storage_path).parent / "metadata_store.json"
            if store_path.exists():
                with open(store_path, "r", encoding="utf-8") as f:
                    meta_store = json.load(f)
                if meta_store:
                    parts = ["### Dokumen Terdaftar & Informasi Penting (Metadata):"]
                    for fn, item in meta_store.items():
                        dtype = item.get("doc_type", "Lainnya")
                        meta = item.get("metadata", {})
                        desc_parts = [f"- Dokumen: {fn}", f"  Tipe: {dtype}"]
                        for k, v in meta.items():
                            if v:
                                if isinstance(v, list):
                                    v = ", ".join(str(x) for x in v)
                                desc_parts.append(f"  {k.capitalize()}: {v}")
                        parts.append("\n".join(desc_parts))
                    metadata_content = "\n".join(parts)
                    
                    meta_doc = {
                        "document": {
                            "file_name": "Workspace_Metadata_Index",
                            "title": "Workspace Metadata Index",
                            "type": "metadata_index",
                            "content": metadata_content
                        },
                        "score": 1.0, # High similarity score to rank first
                        "snippet": metadata_content,
                        "block_type": "metadata_index",
                        "citation": {"page": "Index", "block_type": "metadata_index", "source": "Workspace Metadata Index"}
                    }
                    meta_results.append(meta_doc)
        except Exception as e:
            print(f"[RAG] ⚠️ Error building metadata index for search: {e}")

        # Fetch primary search results
        results = []
        if self.use_embeddings:
            query_embedding = self.embedder.embed_query(query)
            results = self.vector_store.search(query_embedding, top_k=top_k)
            # Filter distance score <= 0.0 to prevent zero-vector/unrelated pollutions
            results = [r for r in results if r.get("score", 0) > 0.0]
        else:
            results = self.simple_rag.search(query, top_k=top_k)

        # Merge and return
        return meta_results + results

    def query(self, text: str) -> Dict[str, Any]:
        """
        High-level query method for Voice/Chat agents.
        Retrieves context from Local Docs AND Web Search if needed.
        
        Args:
            text: User query
            
        Returns:
            Dict with 'answer' (context string) and 'sources'
        """
        print(f"[RAG] Processing query: {text}")
        
        # 1. Local Search
        local_results = self.search(text, top_k=3)
        
        # 2. Check Relevance (simple heuristic: score > 0.7)
        # If we have no results or low scores, trigger web search
        needs_web = False
        if not local_results:
            needs_web = True
            print("[RAG] No local results found. Triggering Web Search...")
        elif local_results and local_results[0].get('score', 0) < 0.65:
            # Score threshold might need tuning for Inner Product
            needs_web = True
            print(f"[RAG] Low confidence ({local_results[0].get('score'):.2f}). Triggering Web Search...")
            
        web_results = []
        if needs_web and self.web_search.is_available():
            web_results = self.web_search.search(text, max_results=3)
            
        # 3. Combine Results
        combined_context = []
        sources = []
        
        # Add Local
        if local_results:
            combined_context.append("### Local Research Data:")
            for rank, item in enumerate(local_results, 1):
                snippet = item.get('snippet', '')
                fname = item.get('document', {}).get('file_name', 'Unknown')
                citation = item.get('citation', {})
                page = citation.get('page')
                block_type = item.get('block_type', 'document')
                citation_label = f" p{page}" if page is not None else ""
                combined_context.append(f"[{rank}] {block_type}{citation_label}: {snippet} (Source: {fname})")
                sources.append(fname)

        # Add Web
        if web_results:
            combined_context.append("\n### Web Search Results:")
            for rank, item in enumerate(web_results, 1):
                title = item['document']['title']
                snippet = item['snippet']
                url = item['document']['url']
                combined_context.append(f"[Web {rank}] {title}: {snippet} (Source: {url})")
                sources.append(url)
                
        if not combined_context:
            return {"answer": "I could not find any relevant information in your documents or on the web.", "sources": []}
            
        return {
            "answer": "\n".join(combined_context),
            "sources": sources
        }
    
    def _chunk_text(self, text: str, chunk_size: int = 512, overlap: int = 128) -> List[str]:
        """
        Split text into overlapping chunks.
        
        Args:
            text: Text to chunk
            chunk_size: Size of each chunk in characters
            overlap: Overlap between chunks
            
        Returns:
            List of text chunks
        """
        chunks = []
        start = 0
        
        while start < len(text):
            end = start + chunk_size
            chunk = text[start:end]
            chunks.append(chunk)
            start = end - overlap
        
        return chunks
    
    def list_documents(self) -> List[Dict[str, str]]:
        """List indexed documents"""
        if self.use_embeddings:
            # Get unique file names from vector store
            files = {}
            for doc in self.vector_store.documents:
                fname = doc.get('file_name', 'Unknown')
                if fname not in files:
                    files[fname] = {
                        "name": fname,
                        "type": doc.get('type', 'Unknown'),
                        "path": doc.get('file_path', 'N/A')
                    }
            return list(files.values())
        else:
            return self.simple_rag.list_documents()
