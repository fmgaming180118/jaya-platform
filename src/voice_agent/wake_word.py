
import os
import logging
import openwakeword
from openwakeword.model import Model
import numpy as np

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("WakeWord")

class WakeWordDetector:
    def __init__(self, model_names=["hey_jarvis_v0.1"], inference_framework="onnx"):
        """
        Initialize the WakeWordDetector.
        mnodel_names: List of model names or paths to .onnx models.
        """
        # Load openwakeword models
        # If specific "jaya" model exists in data/models, load it
        custom_model_path = os.path.join("data", "models", "jaya.onnx")
        if os.path.exists(custom_model_path):
            model_names.append(custom_model_path)
            logger.info(f"Loaded custom Jaya model from {custom_model_path}")
        else:
            logger.warning("Custom 'Jaya' model not found. Using default 'hey_jarvis' as placeholder.")
            if "hey_jarvis_v0.1" not in model_names:
                model_names.append("hey_jarvis_v0.1")

        try:
            openwakeword.utils.download_models(model_names) # Ensure models are downloaded
            self.model = Model(wakeword_models=model_names, inference_framework=inference_framework)
            logger.info(f"Wake Word Model initialized: {model_names}")
        except Exception as e:
            logger.error(f"Failed to initialize WakeWordDetector: {e}")
            self.model = None

    def detect(self, audio_chunk):
        """
        Feed audio chunk to the model and return detected wake word (if any).
        audio_chunk: numpy array of audio data (1280 samples @ 16kHz usually)
        """
        if self.model is None:
            return None, 0.0

        # Feed to model
        # openwakeword expects numpy array (int16 or float32)
        # We assume input is proper format (handled by consumer)
        prediction = self.model.predict(audio_chunk)
        
        # Check predictions
        for label, score in prediction.items():
            if score > 0.5: # Generic threshold, can be tuned
                return label, score
        
        return None, 0.0
