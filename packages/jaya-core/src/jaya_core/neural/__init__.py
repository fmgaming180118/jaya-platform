"""
neural package — Neural Network components for JAYA Core.

Provides:
- TinyNeuralNet: Small neural network (<10M params) for specific tasks
- NeuralSymbolicInterface: Bridge between neural net and symbolic reasoner
- SimpleTokenizer: Simple tokenizer for neural net
"""

from __future__ import annotations

from .tiny_net import (
    TinyNeuralNet,
    TinyNetConfig,
)
from .symbolic_interface import (
    NeuralSymbolicInterface,
    SimpleTokenizer,
    TokenizerConfig,
    TinyNetConfig,
    NeuralSymbolicConfig,
    create_neural_symbolic_interface,
)

__all__ = [
    "TinyNeuralNet",
    "TinyNetConfig",
    "NeuralSymbolicInterface",
    "SimpleTokenizer",
    "TokenizerConfig",
    "NeuralSymbolicConfig",
    "create_neural_symbolic_interface",
]