import numpy as np
import faiss
import os

def test_faiss_integration():
    print("Testing FAISS...")
    
    # 1. Create dummy data
    d = 64                           # dimension
    nb = 1000                        # database size
    nq = 5                           # queries
    
    np.random.seed(1234)             # make reproducible
    xb = np.random.random((nb, d)).astype('float32')
    xb[:, 0] += np.arange(nb) / 1000.
    xq = np.random.random((nq, d)).astype('float32')
    xq[:, 0] += np.arange(nq) / 1000.

    # 2. Build index
    index = faiss.IndexFlatL2(d)   # build the index
    print(f"Is trained? {index.is_trained}")
    index.add(xb)                  # add vectors to the index
    print(f"ntotal: {index.ntotal}")

    # 3. Search
    k = 4                          # we want to see 4 nearest neighbors
    D, I = index.search(xq, k)     # actual search
    
    print("\nResults (Indices):")
    print(I[:5])                   # neighbors of the 5 first queries
    print("\nResults (Distances):")
    print(D[:5])

    # 4. Save/Load
    faiss.write_index(index, "test.index")
    print("\nIndex saved to test.index")
    
    loaded_index = faiss.read_index("test.index")
    print(f"Loaded ntotal: {loaded_index.ntotal}")
    
    # Cleanup
    if os.path.exists("test.index"):
        os.remove("test.index")

if __name__ == "__main__":
    test_faiss_integration()
