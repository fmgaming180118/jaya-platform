
import random
from jaya_research.engine import Value

class Module:
    def zero_grad(self):
        for p in self.parameters():
            p.grad = 0

    def parameters(self):
        return []

class Neuron(Module):
    def __init__(self, nin, nonlin=True):
        self.w = [Value(random.uniform(-1,1)) for _ in range(nin)]
        self.b = Value(0)
        self.nonlin = nonlin

    def __call__(self, x):
        act = sum((wi*xi for wi,xi in zip(self.w, x)), self.b)
        return act.tanh() if self.nonlin else act

    def parameters(self):
        return self.w + [self.b]

    def __repr__(self):
        return f"{'TanH' if self.nonlin else 'Linear'}Neuron({len(self.w)})"

class Layer(Module):
    def __init__(self, nin, nout, **kwargs):
        self.neurons = [Neuron(nin, **kwargs) for _ in range(nout)]

    def __call__(self, x):
        out = [n(x) for n in self.neurons]
        return out[0] if len(out) == 1 else out

    def parameters(self):
        return [p for n in self.neurons for p in n.parameters()]

    def __repr__(self):
        return f"Layer of [{', '.join(str(n) for n in self.neurons)}]"

class MLP(Module):
    def __init__(self, nin, nouts):
        sz = [nin] + nouts
        self.layers = [Layer(sz[i], sz[i+1], nonlin=i!=len(nouts)-1) for i in range(len(nouts))]

    def __call__(self, x):
        for layer in self.layers:
            x = layer(x)
        return x

    def parameters(self):
        return [p for layer in self.layers for p in layer.parameters()]

    def __repr__(self):
        return f"MLP of [{', '.join(str(layer) for layer in self.layers)}]"

class MicroAGI(Module):
    def __init__(self, vocab_size, embed_dim=16, hidden_dim=32):
        # We need a custom Embedding layer
        # For MicroGrad, embedding is just a lookup table of Values
        self.vocab_size = vocab_size
        self.embed_dim = embed_dim
        
        # Init Embeddings: List of List of Values
        self.embeddings = [[Value(random.uniform(-0.1, 0.1), label=f"emb_{i}_{j}") 
                           for j in range(embed_dim)] for i in range(vocab_size)]
        
        # Simple RNN / MLP
        # Input to MLP: embed_dim + hidden_dim
        # Output: hidden_dim + vocab_size (logic and prediction)
        # Actually let's do a simple MLP: Char -> Embed -> MLP -> Logits
        # No RNN state for the very first step to keep graph small? 
        # With MicroGrad, graph grows huge with RNN.
        # Let's stick to simple context window: Input 3 chars -> Predict 1 char.
        
        self.context_length = 3
        self.mlp = MLP(embed_dim * self.context_length, [hidden_dim, vocab_size])

    def parameters(self):
        emb_params = [p for row in self.embeddings for p in row]
        return emb_params + self.mlp.parameters()

    def forward(self, input_indices):
        # input_indices: list of ints of length context_length
        # Gather embeddings
        emb_flat = []
        for idx in input_indices:
            emb_flat.extend(self.embeddings[idx])
            
        # MLP
        logits = self.mlp(emb_flat)
        return logits
    
    def generate(self, start_indices, max_new_tokens, tokenizer=None):
        curr = list(start_indices)
        out = []
        for _ in range(max_new_tokens):
            # Take last 3
            if len(curr) < self.context_length:
                # Pad
                ctx = [0] * (self.context_length - len(curr)) + curr
            else:
                ctx = curr[-self.context_length:]
                
            logits = self.forward(ctx)
            
            # Greedy Argmax
            # Extract data from Values
            probs = [l.data for l in logits]
            next_idx = probs.index(max(probs))
            
            out.append(next_idx)
            curr.append(next_idx)
            
        if tokenizer:
            return tokenizer.decode(out)
        return out
