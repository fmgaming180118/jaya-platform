# Jaya Knowledge Distillation via NVIDIA NIM API

This folder contains a lightweight setup for distilling knowledge from a NVIDIA NIM model (e.g., nemotron-3-8b-instruct) into Jaya's AgenticRAG.

## Contents

- `requirements.txt`: Minimal Python dependencies (requests, tqdm, numpy, tokenizers).
- `distill_via_nim.py`: Main script that queries the NIM API for a list of prompts and collects the responses.
- `sample_prompts.txt`: Example prompts to distill knowledge about Jaya, AI, and related concepts.
- `README.md`: This file.

## Usage

1. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Set environment variables** for the NIM API:
   ```bash
   export NIM_API_URL="https://ai.api.nvidia.com/v1/nim/<model-name>"
   export NIM_API_KEY="your-nim-api-key"
   # Optional: if the model is not specified in the URL
   export NIM_MODEL="nemotron-3-8b-instruct"
   ```

3. **Run the distillation script**:
   ```bash
   python distill_via_nim.py --prompts sample_prompts.txt --output-json distilled_knowledge.json
   ```
   This will query the NIM API for each prompt and save the results to `distilled_knowledge.json`.

4. **Ingest the knowledge into Jaya** (optional step):
   The script currently does not automatically inject the knowledge into Jaya's AgenticRAG to avoid breaking the JayaCore/JayaResearch boundary. To ingest the knowledge, you can:
   - Use the public API of JayaCore (if a method for memorizing arbitrary facts is available) or
   - Add a public method to JayaCore's `IronEngine` or `AgenticRAG` for ingesting facts from distillation (requires a JayaCore change).
   - Alternatively, you can write a small script that uses the `IronEngine` instance (as in the distillation script) to call the internal `memorize` method of `AgenticRAG` (accessible via `engine._agentic_rag` for experimental purposes).

   Example (experimental, accessing private attribute):
   ```python
   from src.brain_v2.engine.runtime import IronEngine
   engine = IronEngine(model_path="JAYA_CORE/JAYA_SOVEREIGN_V18.jay", password="x", enable_twin=False)
   engine.ignite()
   for item in distilled_knowledge:
       engine._agentic_rag.memorize(topic=item["prompt"], content=item["response"], source="nim_distillation", importance=5)
   ```

## Notes

- The NIM API used should be a lightweight model to keep the distillation process fast and inexpensive.
- The prompts in `sample_prompts.txt` are focused on Jaya and AI concepts to help Jaya's internal knowledge base.
- The distilled knowledge is stored as facts in Jaya's AgenticRAG, which can be recalled via the `query_agentic_rag` method or used to enhance the `chat` responses.

## Boundary Considerations

This distillation process respects the JayaCore/JayaResearch boundary by:
- Keeping the NIM API client and distillation logic in JayaResearch.
- Only interacting with JayaCore through the public `IronEngine` interface (initialization and ignition).
- Not adding any direct imports from JayaResearch into JayaCore.
- Leaving the actual ingestion of knowledge as an optional step that the user can implement in a way that maintains the boundary (e.g., by adding a public method in JayaCore if desired).

For production use, consider adding a public method to `IronEngine` or `AgenticRAG` in JayaCore to ingest facts from external sources, which would then be called from this distillation script.