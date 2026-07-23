
import sys
from pathlib import Path

import numpy as np

# Add project root
# Fix path: This file is in src/brain_v2/education
# We need to go up 3 levels to reach project root (d:\Kampus\coba-coba\jaya-research)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.append(str(PROJECT_ROOT))
print(f"Debug: Project Root at {PROJECT_ROOT}")

from src.brain_v2.model.ternary import TernaryLinear


class LogicTrainer:
    """
    Pillar 27: Ternary Precision Education.

    Since weights are discrete {-1, 0, 1}, standard gradient descent is hard.
    We use 'Micro-Evolution': Randomly flip weights and keep if Loss decreases.
    """

    def __init__(self):
        # Neural Net for XOR (Requires specific structure)
        # Input: 2 -> Hidden: 4 -> Output: 1
        self.l1 = TernaryLinear(2, 4)
        self.l2 = TernaryLinear(4, 1)

    def forward(self, x):
        h = self.l1.forward(x)
        h = np.tanh(h) # Activation
        o = self.l2.forward(h)
        return o[0]

    def compute_loss(self, data, labels):
        error = 0.0
        for x, y in zip(data, labels):
            pred = self.forward(x)
            # Binary Cross Entropy-ish (or MSE)
            error += (pred - y) ** 2
        return error

    def mutate(self, amount=1):
        """
        Randomly flip 'amount' weights in a random layer.
        """
        layer = self.l1 if np.random.rand() > 0.5 else self.l2

        # Pick random weight coords
        r, c = layer.weights.shape
        i = np.random.randint(0, r)
        j = np.random.randint(0, c)

        # Save old
        old_val = layer.weights[i,j]

        # Mutate to {-1, 0, 1}
        choices = [-1, 0, 1]
        layer.weights[i,j] = np.random.choice(choices)

        return layer, i, j, old_val

    def train(self, gate_name="XOR", steps=1000):
        print(f"--- Teaching {gate_name} to Iron Body ---")

        # Dataset
        # Inputs: [0,0], [0,1], [1,0], [1,1]
        # XOR Targets: 0, 1, 1, 0
        data = np.array([[0,0], [0,1], [1,0], [1,1]], dtype=np.float32)
        if gate_name == "XOR":
            targets = np.array([0, 1, 1, 0], dtype=np.float32)
        elif gate_name == "AND":
            targets = np.array([0, 0, 0, 1], dtype=np.float32)
        elif gate_name == "OR":
            targets = np.array([0, 1, 1, 1], dtype=np.float32)

        best_loss = self.compute_loss(data, targets)
        print(f"Initial Loss: {best_loss:.4f}")

        for step in range(steps):
            # Mutate
            layer, i, j, old_val = self.mutate()

            # Check new loss
            new_loss = self.compute_loss(data, targets)

            if new_loss < best_loss:
                best_loss = new_loss
                # Keep mutation
                # print(f"Step {step}: Improved Loss -> {best_loss:.4f}")
            else:
                # Revert
                layer.weights[i,j] = old_val

            if best_loss < 0.1:
                print(f"Converged at step {step}! Loss: {best_loss:.4f}")
                break

        print(f"Final Loss: {best_loss:.4f}")
        return best_loss

if __name__ == "__main__":
    trainer = LogicTrainer()
    trainer.train("OR")
    trainer.train("AND")
    trainer.train("XOR") # Hardest
