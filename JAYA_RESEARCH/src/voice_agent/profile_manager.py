import sys, os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from config import config

import os
import numpy as np
import logging
from resemblyzer import VoiceEncoder, preprocess_wav
from pathlib import Path
import time

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ProfileManager")

class ProfileManager:
    def __init__(self, data_dir=config.VOICE_PROFILES_DIR, sample_dir=config.VOICE_SAMPLES_DIR):
        self.data_dir = Path(data_dir)
        self.sample_dir = Path(sample_dir)
        self.encoder = VoiceEncoder()
        
        # Ensure directories exist
        self.data_dir.mkdir(parents=True, exist_ok=True)
        (self.sample_dir / "raw").mkdir(parents=True, exist_ok=True)
        
        self.master_profile_path = self.data_dir / "user_jaya.npy"
        self.master_embedding = None
        self.load_profiles()

    def load_profiles(self):
        """Loads the master voice profile if it exists."""
        if self.master_profile_path.exists():
            try:
                self.master_embedding = np.load(self.master_profile_path)
                logger.info(f"Loaded master profile from {self.master_profile_path}")
            except Exception as e:
                logger.error(f"Failed to load master profile: {e}")
                self.master_embedding = None
        else:
            logger.warning("No master profile found. Please run enrollment.")
            self.master_embedding = None

    def enroll_user(self, audio_paths, save=True):
        """
        Generates an embedding from a list of audio file paths and saves it as the master profile.
        """
        embeddings = []
        for p in audio_paths:
            try:
                wav = preprocess_wav(p)
                embed = self.encoder.embed_utterance(wav)
                embeddings.append(embed)
            except Exception as e:
                logger.error(f"Error processing {p}: {e}")
        
        if not embeddings:
            logger.error("No valid embeddings generated.")
            return False

        # Create master embedding by averaging
        master_embed = np.mean(embeddings, axis=0)
        self.master_embedding = master_embed / np.linalg.norm(master_embed) # Normalize

        if save:
            np.save(self.master_profile_path, self.master_embedding)
            logger.info(f"Saved master profile to {self.master_profile_path}")
        
        return True

    def verify_speaker(self, audio_chunk, threshold=0.75):
        """
        Verifies if the audio chunk belongs to the enrolled user.
        audio_chunk: Raw audio data (numpy array or bytes)
        threshold: Cosine similarity threshold (0.7-0.8 is usually good)
        """
        if self.master_embedding is None:
             # If no profile, we can't verify, so we default to True (open mode) or False (strict)
             # Defaulting to True for now to not block usage, but logging warning
             # logger.warning("Verification called but no profile exists. Allowing.")
             return True, 0.0

        try:
            # Preprocess raw audio if needed, VoiceEncoder expects wav/array
            # If audio_chunk is raw bytes (int16), convert to float32 -1..1
            if isinstance(audio_chunk, bytes):
                 audio_data = np.frombuffer(audio_chunk, dtype=np.int16).astype(np.float32) / 32768.0
            else:
                 audio_data = audio_chunk

            embed = self.encoder.embed_utterance(audio_data)
            
            # Cosine similarity
            similarity = np.dot(embed, self.master_embedding) / (np.linalg.norm(embed) * np.linalg.norm(self.master_embedding))
            
            is_verified = similarity > threshold
            return is_verified, similarity

        except Exception as e:
            logger.error(f"Verification error: {e}")
            return False, 0.0

    def continuous_verification(self, audio_stream_generator, threshold=0.75):
        """
        Generator that yields only verified audio chunks from an input stream.
        """
        for chunk in audio_stream_generator:
            is_verified, score = self.verify_speaker(chunk, threshold)
            if is_verified:
                yield chunk
            else:
                # logger.debug(f"Rejected chunk. Score: {score:.2f}")
                pass
