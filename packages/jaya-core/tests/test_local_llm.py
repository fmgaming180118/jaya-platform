import sys
sys.path.insert(0, '.')

from jaya_core.ai_connectors.local_llm_adapter import LocalLLMAdapter

adapter = LocalLLMAdapter(model_path='JAYA_CORE/models/tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf', n_ctx=512, n_threads=4)
print(f'Model loaded: {adapter.model is not None}')

if adapter.model:
    prompts = ['Halo', 'Apa itu Python?', 'Buatkan fungsi fibonacci', 'Terima kasih']
    for p in prompts:
        response = adapter.generate(p)
        print(f'Prompt: {p}')
        print(f'Response: "{response}"')
        print('---')
else:
    print('Model failed to load')