"""
Meta-Analysis Tool for JAYA Research
Synthesizes multiple research reports into a comprehensive knowledge base
"""
import sys
import os
import json
import time
from pathlib import Path
from typing import List, Dict, Any

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from teacher import Teacher
from research.config import get_config
from memory import DiscoveryMemory


class MetaAnalyst:
    """
    Synthesizes knowledge from multiple research reports.
    "The Chief Scientist" role.
    """
    
    def __init__(self):
        self.config = get_config()
        self.teacher = Teacher()
        # Use main evolution memory
        self.memory = DiscoveryMemory("data/evolution_memory.json")
        
    def get_research_history(self, topic_filter: str = None) -> List[Dict[str, Any]]:
        """
        Retrieve research reports from memory.
        """
        reports = [
            entry for entry in self.memory.history 
            if entry.get('result') == 'RESEARCH_REPORT'
        ]
        
        if topic_filter:
            reports = [
                r for r in reports 
                if topic_filter.lower() in r.get('metadata', {}).get('topic', '').lower()
            ]
            
        return reports
    
    def run_meta_analysis(self, topic: str, lookback_days: int = 30) -> str:
        """
        Synthesize recent research on a topic into a meta-report.
        """
        print(f"[META] 🧠 Starting Meta-Analysis on: {topic}")
        
        # Filter reports by time
        cutoff_time = time.time() - (lookback_days * 86400)
        reports = self.get_research_history(topic)
        recent_reports = [r for r in reports if r['timestamp'] > cutoff_time]
        
        if not recent_reports:
            print("[META] ⚠️  No relevant research reports found.")
            return "No research data available for meta-analysis."
        
        print(f"[META] Found {len(recent_reports)} relevant reports.")
        
        # Extract summaries (limit length to fit context)
        summaries = []
        for i, r in enumerate(recent_reports, 1):
            metadata = r.get('metadata', {})
            content = r.get('code', '')[:2000] # truncate
            summaries.append(f"--- Report {i}: {metadata.get('topic')} ---\n{content}\n")
            
        combined_summaries = "\n".join(summaries)
        
        # Generate Meta-Report
        prompt = self.config.get_prompt(
            'meta_analysis',
            topic=topic,
            summaries=combined_summaries
        )
        
        print("[META] Synthesizing State of the Union report...")
        meta_report = self.teacher.suggest_optimization(
            prompt,
            focus="Meta-Analysis"
        )
        
        # Save
        self._save_meta_report(topic, meta_report)
        
        return meta_report
        
    def _save_meta_report(self, topic: str, content: str):
        """Save meta-report to file and memory"""
        timestamp = int(time.time())
        filename = f"META_{topic.replace(' ', '_')}_{timestamp}.md"
        path = os.path.join(self.config.reports_dir, filename)
        
        os.makedirs(os.path.dirname(path), exist_ok=True)
        
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
            
        print(f"[META] 💾 Meta-Report saved: {path}")
        
        # Store in memory as a high-level insight
        self.memory.add_experience(
            code=content,
            result="META_ANALYSIS",
            metadata={
                "topic": topic,
                "reports_analyzed": len(self.get_research_history(topic)),
                "path": path,
                "timestamp": time.time()
            }
        )

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("topic", help="Topic to analyze (e.g. 'Compiler')")
    parser.add_argument("--days", type=int, default=30, help="Lookback days")
    args = parser.parse_args()
    
    analyst = MetaAnalyst()
    report = analyst.run_meta_analysis(args.topic, args.days)
    print("\n" + "="*60)
    print(report[:500] + "..." if len(report) > 500 else report)
