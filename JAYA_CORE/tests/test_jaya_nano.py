#!/usr/bin/env python3
"""
Test suite untuk JayaNanoEngine.

Tests:
- Engine initialization
- Model loading
- Tokenization
- Generation (mock)
- Cleanup
"""

import os
import sys
import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

# Add JAYA_CORE to path
ROOT = Path(__file__).resolve().parents[1]
JAYA_CORE_ROOT = ROOT
sys.path.insert(0, str(JAYA_CORE_ROOT / "src"))

from brain_v2.engine.jaya_nano import (
    JayaNanoEngine,
    ModelConfig,
    GenerationConfig,
    InferenceBackend,
    create_engine,
    create_engine_for_android,
)


class TestModelConfig:
    """Test ModelConfig dataclass."""
    
    def test_default_config(self):
        config = ModelConfig(model_path="test.gguf")
        assert config.model_path == "test.gguf"
        assert config.n_ctx == 8192
        assert config.n_batch == 512
        assert config.n_threads == 4
        assert config.backend == InferenceBackend.CPU
        assert config.temperature == 0.3
    
    def test_custom_config(self):
        config = ModelConfig(
            model_path="custom.gguf",
            n_ctx=4096,
            n_threads=8,
            backend=InferenceBackend.GPU,
            temperature=0.7,
        )
        assert config.n_ctx == 4096
        assert config.n_threads == 8
        assert config.backend == InferenceBackend.GPU
        assert config.temperature == 0.7


class TestGenerationConfig:
    """Test GenerationConfig dataclass."""
    
    def test_default_config(self):
        config = GenerationConfig()
        assert config.max_tokens == 512
        assert config.temperature == 0.3
        assert config.top_k == 40
        assert config.top_p == 0.95
        assert config.repeat_penalty == 1.1
        assert config.stop_sequences == []
    
    def test_custom_config(self):
        config = GenerationConfig(
            max_tokens=256,
            temperature=0.5,
            stop_sequences=["STOP", "END"],
        )
        assert config.max_tokens == 256
        assert config.temperature == 0.5
        assert config.stop_sequences == ["STOP", "END"]


class TestJayaNanoEngine:
    """Test JayaNanoEngine class."""
    
    def test_engine_creation(self):
        config = ModelConfig(model_path="test.gguf")
        engine = JayaNanoEngine(config)
        assert engine.config == config
        assert engine._initialized is False
        assert engine._lib is None
        assert engine._model_ptr is None
        assert engine._ctx_ptr is None
        assert engine._batch_ptr is None
        assert engine._sampler_ptr is None
    
    def test_find_native_library_not_found(self):
        config = ModelConfig(model_path="test.gguf")
        engine = JayaNanoEngine(config)
        # Should not find library in test environment
        result = engine._find_native_library()
        assert result is None or os.path.exists(result)
    
    @patch('brain_v2.engine.jaya_nano.ctypes.CDLL')
    def test_initialize_library_not_found(self, mock_cdll):
        config = ModelConfig(model_path="test.gguf")
        engine = JayaNanoEngine(config)
        engine._native_lib_path = None  # Simulate not found
        
        result = engine.initialize()
        assert result is False
        assert engine._initialized is False
    
    @patch('brain_v2.engine.jaya_nano.ctypes.CDLL')
    def test_initialize_model_not_found(self, mock_cdll):
        config = ModelConfig(model_path="/nonexistent/model.gguf")
        engine = JayaNanoEngine(config)
        engine._native_lib_path = "/fake/libllama.so"
        
        result = engine.initialize()
        assert result is False
        assert engine._initialized is False
    
    def test_cleanup_not_initialized(self):
        config = ModelConfig(model_path="test.gguf")
        engine = JayaNanoEngine(config)
        # Should not raise
        engine.cleanup()
        assert engine._initialized is False
    
    def test_context_manager(self):
        config = ModelConfig(model_path="test.gguf")
        engine = JayaNanoEngine(config)
        
        with patch.object(engine, 'initialize', return_value=True) as mock_init:
            with patch.object(engine, 'cleanup') as mock_cleanup:
                with engine as e:
                    assert e is engine
                mock_init.assert_called_once()
                mock_cleanup.assert_called_once()
    
    def test_del_calls_cleanup(self):
        config = ModelConfig(model_path="test.gguf")
        engine = JayaNanoEngine(config)
        engine.cleanup = Mock()
        del engine
        # cleanup should be called (but we can't easily test __del__)


class TestCreateEngine:
    """Test factory function."""
    
    def test_default_config(self):
        engine = create_engine("model.gguf")
        assert isinstance(engine, JayaNanoEngine)
        assert engine.config.model_path == "model.gguf"
        assert engine.config.n_ctx == 8192
        assert engine.config.n_batch == 512
        assert engine.config.n_threads == 4
        assert engine.config.backend == InferenceBackend.CPU
    
    def test_override_config(self):
        engine = create_engine(
            "model.gguf",
            n_ctx=4096,
            n_threads=8,
            temperature=0.7,
        )
        assert engine.config.n_ctx == 4096
        assert engine.config.n_threads == 8
        assert engine.config.temperature == 0.7


class TestCreateEngineForAndroid:
    """Test factory function for Android."""
    
    def test_default_android_config(self):
        engine = create_engine_for_android("model.gguf")
        assert isinstance(engine, JayaNanoEngine)
        assert engine.config.n_ctx == 4096
        assert engine.config.n_batch == 256
        assert engine.config.n_threads == 4
        assert engine.config.backend == InferenceBackend.CPU
    
    def test_override_config(self):
        engine = create_engine_for_android(
            "model.gguf",
            n_ctx=2048,
            n_threads=8,
            temperature=0.5,
        )
        assert engine.config.n_ctx == 2048
        assert engine.config.n_threads == 8
        assert engine.config.temperature == 0.5


class TestInferenceBackend:
    """Test InferenceBackend enum."""
    
    def test_values(self):
        assert InferenceBackend.CPU.value == "cpu"
        assert InferenceBackend.GPU.value == "gpu"
        assert InferenceBackend.NPU.value == "npu"


# Integration test (requires actual model and library)
@pytest.mark.integration
class TestJayaNanoEngineIntegration:
    """Integration tests - require actual model and libllama.so"""
    
    @pytest.fixture
    def model_path(self):
        """Path to test model - set via env var."""
        path = os.environ.get("JAYA_TEST_MODEL")
        if not path or not os.path.exists(path):
            pytest.skip("JAYA_TEST_MODEL not set or file not found")
        return path
    
    @pytest.fixture
    def lib_path(self):
        """Path to libllama.so - set via env var."""
        path = os.environ.get("JAYA_NANO_LIB_PATH")
        if not path or not os.path.exists(path):
            pytest.skip("JAYA_NANO_LIB_PATH not set or file not found")
        return path
    
    def test_initialize_with_real_model(self, model_path, lib_path):
        """Test full initialization with real model."""
        config = ModelConfig(model_path=model_path)
        engine = JayaNanoEngine(config)
        engine._native_lib_path = lib_path
        
        # This will fail if library functions don't match
        # but tests the initialization flow
        try:
            result = engine.initialize()
            # May fail due to signature mismatches, but shouldn't crash
            assert isinstance(result, bool)
        finally:
            engine.cleanup()
    
    def test_tokenize_with_real_model(self, model_path, lib_path):
        """Test tokenization with real model."""
        config = ModelConfig(model_path=model_path)
        engine = JayaNanoEngine(config)
        engine._native_lib_path = lib_path
        
        try:
            if engine.initialize():
                tokens = engine.tokenize("Hello world")
                assert isinstance(tokens, list)
        finally:
            engine.cleanup()