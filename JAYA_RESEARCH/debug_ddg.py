
try:
    from duckduckgo_search import DDGS
    print("[*] DDGS Imported successfully.")
except ImportError:
    print("[!] DDGS not installed.")
    exit()

def debug_search():
    ddgs = DDGS()
    query = "python" # Simple query
    print(f"[*] Searching for: {query}")
    
    try:
        # Try raw generator to see if empty immediately
        gen = ddgs.text(query, max_results=3)
        results = list(gen)
        
        if not results:
             print("[!] No results returned. Possible IP Ban or API change.")
             # Try safe search off?
             # results = list(ddgs.text(query, max_results=3, safesearch='off'))
             
        print(f"[*] Found {len(results)} results.")
        
        for i, r in enumerate(results):
            print(f"\n--- Result {i+1} ---")
            print(f"Keys: {r.keys()}")
            print(f"Title: {r.get('title')}")
            print(f"Body: {r.get('body')}")
            print(f"Href: {r.get('href', r.get('link'))}")
            
    except Exception as e:
        print(f"[!] Error: {e}")

if __name__ == "__main__":
    debug_search()
