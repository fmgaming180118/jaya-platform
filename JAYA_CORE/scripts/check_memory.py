import json

# Load memory
with open('data/evolution_memory.json', encoding='utf-8') as f:
    data = json.load(f)

# Filter variants
variants = [e for e in data if e.get('type') == 'evolution_variant']

print(f"✅ Total evolution variants: {len(variants)}")
print(f"📊 Total memory entries: {len(data)}")

if variants:
    # Sort by score
    sorted_variants = sorted(variants, key=lambda x: x.get('score', 0), reverse=True)
    
    print(f"\n🏆 Top 10 Best Variants:")
    for i, v in enumerate(sorted_variants[:10], 1):
        print(f"  #{i} - Gen {v['generation']}: Score {v['score']:.2f}")
    
    # Check if auto-pruning is working
    if len(variants) > 10:
        print(f"\n⚠️  Warning: {len(variants)} variants found (expected max 10)")
        print("   Auto-pruning may not be working correctly")
    else:
        print(f"\n✅ Auto-pruning working! Only {len(variants)} variants stored")
        
    # Show latest variant
    latest = sorted_variants[0]
    print(f"\n📝 Latest Best Variant:")
    print(f"   Generation: {latest['generation']}")
    print(f"   Score: {latest['score']:.2f}")
    print(f"   Compiler size: {len(latest['compiler'])} bytes")
    print(f"   Syntax size: {len(latest['syntax'])} bytes")
else:
    print("\n❌ No variants found! System may not be saving properly.")
