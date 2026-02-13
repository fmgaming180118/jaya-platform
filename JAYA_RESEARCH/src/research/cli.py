# CLI Interface for JAYA Research Assistant

import os
import sys
import argparse
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from research.agent import ResearchAgent
from research.enhanced_rag import EnhancedRAGClient


def main():
    """Main CLI entry point"""
    parser = argparse.ArgumentParser(
        description="JAYA Research Assistant - AI-powered deep research"
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Research command
    research_parser = subparsers.add_parser('research', help='Conduct research on a topic')
    research_parser.add_argument('topic', type=str, help='Research topic')
    research_parser.add_argument('--max-queries', type=int, default=10, help='Maximum research questions')
    research_parser.add_argument('--output', type=str, help='Output file path')
    research_parser.add_argument('--no-human-loop', action='store_true', help='Skip human approval')
    
    # Ingest command
    ingest_parser = subparsers.add_parser('ingest', help='Ingest documents into RAG')
    ingest_parser.add_argument('files', nargs='+', help='Document files to ingest')
    
    # List command
    list_parser = subparsers.add_parser('list-docs', help='List indexed documents')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    # Execute commands
    if args.command == 'research':
        agent = ResearchAgent(topic=args.topic)
        report = agent.run(human_in_loop=not args.no_human_loop)
        
        if args.output:
            with open(args.output, 'w', encoding='utf-8') as f:
                f.write(report)
            print(f"\n[CLI] Report saved to: {args.output}")
    
    elif args.command == 'ingest':
        rag = EnhancedRAGClient()
        result = rag.ingest_documents(args.files)
        
        print(f"\n[CLI] Ingestion complete!")
        print(f"  Status: {result['status']}")
        print(f"  Files: {result.get('ingested', 0)}")
        print(f"  Chunks: {result.get('chunks', 0)}")
    
    elif args.command == 'list-docs':
        rag = EnhancedRAGClient()
        docs = rag.list_documents()
        
        print(f"\n[CLI] Indexed Documents ({len(docs)}):")
        for i, doc in enumerate(docs, 1):
            print(f"  {i}. {doc['name']} ({doc['type']})")


if __name__ == '__main__':
    main()
