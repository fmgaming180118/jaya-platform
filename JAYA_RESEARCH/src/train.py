
import random
import time
import json
import sys
import os
import math

# Ensure import path
sys.path.append(os.path.dirname(__file__))

from engine import Value
from student import MicroAGI
from tokenizer import CharTokenizer

# Hyperparameters
EPOCHS = 20
LEARNING_RATE = 0.05
CONTEXT_LEN = 3 

def load_data(path="data/seed_dataset.json"):
    path = os.path.join(os.path.dirname(__file__), '..', 'data', 'seed_dataset.json')
    if not os.path.exists(path):
        print(f"[!] Data not found at {path}")
        return []
    with open(path, "r") as f:
        data = json.load(f)
    return data

def train():
    try:
        print("[*] Loading Dataset...")
        raw_data = load_data()
        if not raw_data: return

        tokenizer = CharTokenizer()
        vocab_size = tokenizer.vocab_size
        print(f"[*] Vocab Size: {vocab_size}")
        
        # Init Model
        model = MicroAGI(vocab_size, embed_dim=8, hidden_dim=16) 
        print(f"[*] Model Parameters: {len(model.parameters())}")
        
        # Simple SGD
        print(f"[*] Training on subset of data (Speed Optimization for MicroGrad)...")
        # MicroGrad is slow, so we train on small chunks of text
        subset = raw_data[:3] 
        
        for epoch in range(EPOCHS):
            total_loss = 0
            start_time = time.time()
            
            for item in subset:
                text = item['input_logic'] + "->" + item['output_llvm'][:10] # Shorten for speed
                tokens = tokenizer.encode(text)
                
                # Iterate through text
                for i in range(len(tokens) - CONTEXT_LEN):
                    ctx = tokens[i : i+CONTEXT_LEN]
                    target = tokens[i+CONTEXT_LEN]
                    
                    # Forward
                    logits = model.forward(ctx) # list of Values
                    
                    # Manual Cross Entropy Loss
                    # loss = -log(softmax(logits)[target])
                    #      = -log(exp(logits[target]) / sum(exp(logits)))
                    #      = -logits[target] + log(sum(exp(logits)))
                    
                    target_logit = logits[target]
                    
                    # Sum Exp for Softmax
                    # Naively: sum([l.exp() for l in logits])
                    # Stability fix? standard is max subtraction but allow naive for now
                    exp_sum = Value(0)
                    for l in logits:
                        exp_sum = exp_sum + l.exp()
                    
                    loss = -target_logit + exp_sum.log()
                    
                    # Accumulate
                    # We can backward every step or accumulate gradients
                    # For MicroGrad speed, let's backward every step (SGD)
                    
                    # Zero Grad
                    model.zero_grad()
                    
                    # Backward
                    loss.backward()
                    
                    # Step
                    for p in model.parameters():
                        p.data -= LEARNING_RATE * p.grad
                        
                    total_loss += loss.data
            
            dt = time.time() - start_time
            print(f"Epoch {epoch}: Loss {total_loss:.4f} (Time: {dt:.2f}s)")
            
            # Test Generation
            if epoch % 5 == 0:
                start_ids = tokenizer.encode("def")
                gen_ids = model.generate(start_ids, max_new_tokens=5)
                print(f"  Gen: {tokenizer.decode(gen_ids)}")

    except Exception as e:
        print(f"[FAIL] {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    train()
