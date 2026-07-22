import os
import logging
import numpy as np

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("WakeWord")

try:
    import openwakeword
    from openwakeword.model import Model
    HAVE_OPENWAKEWORD = True
except ImportError:
    openwakeword = None
    Model = None
    HAVE_OPENWAKEWORD = False


class WakeWordDetector:
    def __init__(self, model_names=["hey_jarvis_v0.1"], inference_framework="onnx"):
        """
        Initialize the WakeWordDetector with fallback support.
        """
        self.model = None
        if not HAVE_OPENWAKEWORD:
            logger.warning("openwakeword not installed. Using software wake word fallback.")
            return

        custom_model_path = os.path.join("data", "models", "jaya.onnx")
        if os.path.exists(custom_model_path):
            model_names.append(custom_model_path)
            logger.info(f"Loaded custom Jaya model from {custom_model_path}")
        else:
            logger.warning("Custom 'Jaya' model not found. Using default 'hey_jarvis' as placeholder.")
            if "hey_jarvis_v0.1" not in model_names:
                model_names.append("hey_jarvis_v0.1")

        try:
            openwakeword.utils.download_models(model_names)
            self.model = Model(wakeword_models=model_names, inference_framework=inference_framework)
            logger.info(f"Wake Word Model initialized: {model_names}")
        except Exception as e:
            logger.error(f"Failed to initialize WakeWordDetector: {e}")
            self.model = None

    def detect(self, audio_chunk):
        """
        Feed audio chunk to the model and return detected wake word (if any).
        """
        if self.model is None:
            return None, 0.0

        try:
            prediction = self.model.predict(audio_chunk)
            for label, score in prediction.items():
                if score > 0.5:
                    return label, score
        except Exception as e:
            logger.error(f"Detection error: {e}")

        return None, 0.0
