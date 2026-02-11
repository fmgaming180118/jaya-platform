# Tutorial: Membangun Pipeline RAG Pemrosesan Dokumen dengan Nemotron

Dokumen ini adalah panduan teknis yang disarikan dari tutorial NVIDIA: *"How to Build a Document Processing Pipeline for RAG with Nemotron"*. Tutorial ini menjelaskan cara membangun pipeline RAG multimodal *production-ready* yang dapat menangani dokumen kompleks (PDF, tabel, grafik).

## Ringkasan Pipeline
Pipeline ini menggunakan **NVIDIA Nemotron** dan **NIM microservices** untuk memecah dokumen, membuat embedding, dan menghasilkan jawaban yang dikutip dengan presisi tinggi.

Komponen utama:
1.  **Extraction**: Menggunakan library `nv-ingest` untuk mengekstrak struktur dokumen.
2.  **Embedding**: Mengubah teks dan gambar menjadi vektor menggunakan `nvidia/llama-nemotron-embed-vl-1b-v2`.
3.  **Reranking**: Menyaring hasil pencarian dengan `nvidia/llama-nemotron-rerank-vl-1b-v2`.
4.  **Generation**: Menghasilkan jawaban menggunakan `Llama-3.3-Nemotron-Super-49B`.

## Tantangan Dokumen Tradisional
- **Kompleksitas Struktur**: Tabel dan matriks sering rusak jika diproses sebagai teks biasa.
- **Konten Multimodal**: Informasi penting dalam grafik/diagram sering terlewatkan.
- **Kutipan**: Kebutuhan industri akan audit trail yang presisi.

## Tahapan Implementasi

### 1. Ekstraksi (Extraction)
Mengonversi PDF "pixel dan layout" menjadi unit terstruktur (teks, markdown tabel, gambar grafik).

```python
# Contoh Kode Ekstraksi dengan nv-ingest
# Memulai pipeline ingesti dan klien lokal
client = NvIngestClient(
    message_client_allocator=SimpleClient,
    message_client_port=7671, 
    message_client_hostname="localhost"
)

# Submit job ekstraksi: tabel sebagai Markdown + crop grafik
ingestor = (Ingestor(client=client)
    .files([PDF_PATH])
    .extract(
        extract_text=True,
        extract_tables=True,
        extract_charts=True,  # crop grafik untuk multimodal RAG
        extract_images=False,
        extract_method="pdfium",
        table_output_format="markdown"
    )
)

job_results = ingestor.ingest()
extracted_data = job_results[0]
```

### 2. Embedding
Mengubah setiap item yang diekstrak menjadi vektor dimensi tetap (2048-dim) untuk pencarian kesamaan. Model embedding multimodal Nemotron dapat memproses teks saja, gambar saja, atau campuran keduanya.

```python
# Contoh Kode Embedding
HF_EMBED_MODEL_ID = "nvidia/llama-nemotron-embed-vl-1b-v2"
# ... inisialisasi Milvus Client ...

# Encoding Multimodal
with torch.inference_mode():
    if modality == "image_text":
        emb = embed_model.encode_documents(images=[image_obj], texts=[content_text])
    elif modality == "image":
        emb = embed_model.encode_documents(images=[image_obj])
    else:
        emb = embed_model.encode_documents(texts=[content_text])

# Selanjutnya simpan vektor ke database vektor (misal: Milvus)
```

### 3. Reranking
Lapisan presisi setelah pencarian awal. Karena melakukan cross-encoding mahal, ini hanya dilakukan pada *shortlist* hasil teratas (top-K) dari database vektor.

```python
# Tahap 1: Pencarian padat (dense retrieval) dari Milvus (high recall)
# ... search milvus ...

# Tahap 2: VLM cross-encoder rerank (query + doc_text + optional doc_image) (high precision)
batch = rerank_inputs[i:i+batch_size] 
inputs = rerank_processor.process_queries_documents_crossencoder(batch)

with torch.no_grad():
    logits = rerank_model(**inputs).logits.squeeze(-1).float().cpu().numpy()
    
# Hasil reranking digunakan untuk menyortir kandidat sebelum dikirim ke LLM
```

### 4. Generation
Menggunakan model `Llama-3.3-Nemotron-Super-49B` yang menerima dokumen teratas + pertanyaan pengguna, dan menghasilkan jawaban yang "grounded" (berdasar) dengan kutipan yang jelas.

## Sumber Daya Tambahan
- [Jupyter Notebook Tutorial (GitHub)](https://github.com/NVIDIA-NeMo/Nemotron/tree/chiachihc/IDP_use_case/use-case-examples/Intelligent%20Document%20Processing%20with%20Nemotron%20RAG)
- [NVIDIA NIM Microservices](https://developer.nvidia.com/nim)
