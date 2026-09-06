# CLI Interface for JAYA Research Assistant

import json
import os
import sys
import argparse
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from jaya_research.research.agent import ResearchAgent
from jaya_research.research.enhanced_rag import EnhancedRAGClient
from jaya_research.research.academic.journal_processor import JournalProcessor
from jaya_research.research.recursive_research import RecursiveResearchLoop
from jaya_research.research.workspace_manager import WorkspaceManager


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

    # ── ingest-pdf ──────────────────────────────────────────────────────────
    ingest_pdf_parser = subparsers.add_parser('ingest-pdf', help='Ingest PDF files with multimodal extraction')
    ingest_pdf_parser.add_argument('files', nargs='+', help='PDF files to ingest')
    ingest_pdf_parser.add_argument('--workspace', type=str, default='default',
                                   help='Target workspace (default: default)')

    ingest_pdf_parser.add_argument('--inspect', action='store_true',
                                   help='Print extracted PDF block metadata after ingest')

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

    # ── agent ────────────────────────────────────────────────────────────────
    agent_parser = subparsers.add_parser('agent', help='Run an agentic research task')
    agent_parser.add_argument('intent', type=str, help='Task or question to execute')
    agent_parser.add_argument('--workspace', type=str, default='default',
                              help='Workspace name for isolated context')
    agent_parser.add_argument('--focus', type=str, default='General AGI research',
                              help='Optional focus areas for the research agent')
    agent_parser.add_argument('--max-queries', type=int, default=10,
                              help='Maximum number of research queries')
    agent_parser.add_argument('--no-human-loop', action='store_true',
                              help='Skip interactive approval checkpoints')

    # ── recursive ────────────────────────────────────────────────────────────
    recursive_parser = subparsers.add_parser('recursive', help='Run recursive discovery research')
    recursive_parser.add_argument('topic', type=str, help='Starting topic or seed')
    recursive_parser.add_argument('--workspace', type=str, default='default',
                                  help='Workspace name for isolated context')
    recursive_parser.add_argument('--max-iterations', type=int, default=3,
                                  help='Maximum recursive iterations')
    recursive_parser.add_argument('--novelty-threshold', type=float, default=0.65,
                                  help='Minimum novelty confidence required to continue')
    recursive_parser.add_argument('--no-human-loop', action='store_true',
                                  help='Skip interactive approval checkpoints')
    recursive_parser.add_argument('--seed-from-journals', action='store_true',
                                  help='Use free journal results to create the initial recursive seed')
    recursive_parser.add_argument('--seed-max-papers', type=int, default=2,
                                  help='Number of free journal papers to use for seed generation')
    recursive_parser.add_argument('--save', action='store_true',
                                  help='Save result as JSON and Markdown files in workspace')

    # ── journal ──────────────────────────────────────────────────────────────
    journal_parser = subparsers.add_parser('journal', help='Search and summarize free academic papers')
    journal_parser.add_argument('query', type=str, help='Research topic or journal search query')
    journal_parser.add_argument('--max-papers', type=int, default=1,
                                help='Number of papers to fetch and summarize')
    journal_parser.add_argument('--show-sources', action='store_true',
                                help='Print per-paper source and page-aware metadata')
    journal_parser.add_argument('--save', action='store_true',
                                help='Save compact summaries as JSON file in workspace')

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

    elif args.command == 'ingest-pdf':
        ws_paths = wm.get_or_create_paths(args.workspace)
        rag = EnhancedRAGClient(vector_store_path=ws_paths['vector_store'])
        result = rag.ingest_documents(args.files)

        print(f"\n[CLI] PDF ingestion complete!")
        print(f"  Workspace : {args.workspace}")
        print(f"  Status    : {result.get('status', 'unknown')}")
        print(f"  Files     : {result.get('ingested', 0)}")
        print(f"  Chunks    : {result.get('chunks', 0)}")
        if args.inspect and result.get('status') == 'success':
            for file_path in args.files:
                if file_path.lower().endswith('.pdf') and os.path.exists(file_path):
                    pdf_result = rag._ingest_pdf_multimodal(file_path)
                    print(f"\n  [PDF] {os.path.basename(file_path)}")
                    print(f"    Tables   : {pdf_result.get('table_count', 0)}")
                    print(f"    Images   : {pdf_result.get('image_count', 0)}")
                    print(f"    OCR      : {pdf_result.get('ocr_count', 0)}")
                    for idx, block in enumerate(pdf_result.get('documents', [])[:5], 1):
                        print(
                            f"    Block {idx}: {block.get('subtype')} "
                            f"p{block.get('page_number')} o{block.get('order')}"
                        )

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

    elif args.command == 'agent':
        agent = ResearchAgent(topic=args.intent, focus_areas=args.focus, workspace=args.workspace)
        agent.config.max_queries = args.max_queries
        report = agent.run(human_in_loop=not args.no_human_loop)

        print("\n[CLI] JAYA Research Agent complete")
        print(f"  Workspace  : {args.workspace}")
        print(f"  Queries    : {len(agent.queries)}")
        print(f"  Findings   : {len(agent.findings)}")
        print(f"  Graph RAG  : {'enabled' if getattr(agent, 'graph_rag', None) else 'disabled'}")
        print(f"  Report     : {agent.get_report_path()}")
        print(f"  Status     : {'generated' if report else 'empty'}")

    elif args.command == 'recursive':
        loop = RecursiveResearchLoop(workspace=args.workspace)
        seed_topic = args.topic
        if args.seed_from_journals:
            seed_topic = loop.seed_from_journals(args.topic, max_papers=args.seed_max_papers)
            print(f"[CLI] Journal-seeded recursive topic: {seed_topic}")
        result = loop.run(
            topic=seed_topic,
            max_iterations=args.max_iterations,
            novelty_threshold=args.novelty_threshold,
            human_in_loop=not args.no_human_loop,
        )
        print("\n[CLI] JAYA Recursive Research complete")
        print(f"  Topic      : {result.topic}")
        print(f"  Workspace  : {result.workspace}")
        print(f"  Iterations : {result.iterations}")
        print(f"  Stopped    : {result.stopped_reason}")
        print(f"  Steps      : {len(result.steps)}")
        
        if args.save:
            saved = loop.save_result(result)
            print(f"  Saved JSON : {saved['json']}")
            print(f"  Saved MD   : {saved['markdown']}")

    elif args.command == 'journal':
        processor = JournalProcessor()
        result = processor.process_query(args.query, max_papers=args.max_papers)
        print("\n[CLI] Free academic journal search complete")
        print("  Sources   : ArXiv + Semantic Scholar + OpenAlex")
        print(f"  Status    : {result.get('status', 'unknown')}")
        print(f"  Papers    : {len(result.get('papers', []))}")
        if result.get('papers'):
            for idx, paper in enumerate(result['papers'], 1):
                meta = paper.get('metadata', {})
                print(f"  {idx}. {meta.get('title', 'Unknown')}")
                print(f"     Source : {meta.get('source', 'Unknown')}")
                print(f"     Rank   : {meta.get('rank_score', 0):.2f}")
                if args.show_sources:
                    print(f"     Link   : {meta.get('pdf_link') or meta.get('landing_page_url') or 'N/A'}")
                    summary = paper.get('summary', '')
                    if summary:
                        print(f"     Note   : {summary[:240]}")

        if args.save and result.get('papers'):
            wm = WorkspaceManager()
            ws_paths = wm.get_or_create_paths(args.workspace)
            out_dir = Path(ws_paths['root'])
            out_dir.mkdir(parents=True, exist_ok=True)
            json_path = out_dir / "journal_compact.json"
            compact_list = [
                p.get('compact_summary')
                for p in result['papers']
                if p.get('compact_summary')
            ]
            json_path.write_text(json.dumps(compact_list, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"  Saved JSON : {json_path}")


if __name__ == '__main__':
    main()
