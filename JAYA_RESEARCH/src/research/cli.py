# CLI Interface for JAYA Research Assistant

import os
import sys
import argparse
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from research.agent import ResearchAgent
from research.enhanced_rag import EnhancedRAGClient
from research.workspace_manager import WorkspaceManager


def main():
    """Main CLI entry point"""
    parser = argparse.ArgumentParser(
        description="JAYA Research Assistant - AI-powered deep research"
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # ── research ──────────────────────────────────────────────────────────────
    research_parser = subparsers.add_parser('research', help='Conduct research on a topic')
    research_parser.add_argument('topic', type=str, help='Research topic')
    research_parser.add_argument('--workspace', type=str, default='default',
                                 help='Workspace name for isolated RAG memory (default: default)')
    research_parser.add_argument('--max-queries', type=int, default=10,
                                 help='Maximum research questions')
    research_parser.add_argument('--output', type=str, help='Output file path')
    research_parser.add_argument('--no-human-loop', action='store_true',
                                 help='Skip human approval')

    # ── ingest ────────────────────────────────────────────────────────────────
    ingest_parser = subparsers.add_parser('ingest',
                                          help='Ingest documents or YouTube URLs into RAG')
    ingest_parser.add_argument('files', nargs='+',
                               help='Document files or YouTube URLs to ingest')
    ingest_parser.add_argument('--workspace', type=str, default='default',
                               help='Target workspace (default: default)')

    # ── list-docs ─────────────────────────────────────────────────────────────
    list_parser = subparsers.add_parser('list-docs', help='List indexed documents')
    list_parser.add_argument('--workspace', type=str, default='default',
                             help='Workspace to inspect (default: default)')

    # ── workspace-list ────────────────────────────────────────────────────────
    subparsers.add_parser('workspace-list', help='List all research workspaces')

    # ── workspace-create ──────────────────────────────────────────────────────
    wsc_parser = subparsers.add_parser('workspace-create', help='Create a new workspace')
    wsc_parser.add_argument('name', type=str, help='Workspace name')
    wsc_parser.add_argument('--description', type=str, default='',
                            help='Optional description')

    # ── workspace-delete ──────────────────────────────────────────────────────
    wsd_parser = subparsers.add_parser('workspace-delete',
                                       help='Delete a workspace and all its data')
    wsd_parser.add_argument('name', type=str, help='Workspace ID to delete')

    # ─────────────────────────────────────────────────────────────────────────
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    wm = WorkspaceManager()

    # ── Execute commands ──────────────────────────────────────────────────────
    if args.command == 'research':
        agent = ResearchAgent(topic=args.topic, workspace=args.workspace)
        report = agent.run(human_in_loop=not args.no_human_loop)
        
        if args.output:
            with open(args.output, 'w', encoding='utf-8') as f:
                f.write(report)
            print(f"\n[CLI] Report saved to: {args.output}")

    elif args.command == 'ingest':
        ws_paths = wm.get_or_create_paths(args.workspace)
        rag = EnhancedRAGClient(vector_store_path=ws_paths['vector_store'])
        result = rag.ingest_documents(args.files)
        
        print(f"\n[CLI] Ingestion complete!")
        print(f"  Workspace : {args.workspace}")
        print(f"  Status    : {result.get('status', 'unknown')}")
        print(f"  Files     : {result.get('ingested', 0)}")
        print(f"  Chunks    : {result.get('chunks', 0)}")

    elif args.command == 'list-docs':
        ws_paths = wm.get_or_create_paths(args.workspace)
        rag = EnhancedRAGClient(vector_store_path=ws_paths['vector_store'])
        docs = rag.list_documents()
        
        print(f"\n[CLI] Indexed Documents in workspace '{args.workspace}' ({len(docs)}):")
        for i, doc in enumerate(docs, 1):
            print(f"  {i}. {doc['name']} ({doc['type']})")

    elif args.command == 'workspace-list':
        workspaces = wm.list_workspaces()
        print(f"\n[CLI] Research Workspaces ({len(workspaces)}):")
        for ws in workspaces:
            print(f"  📂 {ws.get('id', ws.get('name'))} — {ws.get('description', '')}")

    elif args.command == 'workspace-create':
        result = wm.create_workspace(args.name, description=args.description)
        if result['status'] == 'success':
            print(f"\n[CLI] ✅ Workspace '{args.name}' created (ID: {result['id']})")
        else:
            print(f"\n[CLI] ❌ {result['message']}")

    elif args.command == 'workspace-delete':
        result = wm.delete_workspace(args.name)
        if result['status'] == 'success':
            print(f"\n[CLI] 🗑️  {result['message']}")
        else:
            print(f"\n[CLI] ❌ {result['message']}")


if __name__ == '__main__':
    main()
