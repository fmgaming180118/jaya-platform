"""
Semantic AST parser for JAYA Librarian Core.
Treats code as a semantic library rather than plain text.
Extracts symbols, signatures, docstrings, and builds a Code Symbol Graph.
"""

import ast
from dataclasses import dataclass, field
from typing import List, Dict, Set, Optional

@dataclass
class CodeSymbol:
    source_id: str
    file_path: str
    symbol_name: str
    symbol_type: str  # 'function', 'class', 'method'
    signature: str
    docstring: Optional[str]
    source_span: str  # e.g., "L10-L25"
    calls: List[str] = field(default_factory=list)
    called_by: List[str] = field(default_factory=list)
    tests: List[str] = field(default_factory=list)
    imports: List[str] = field(default_factory=list)
    version: str = "v1"
    
    @property
    def canonical_id(self) -> str:
        return f"{self.source_id}@{self.version}:{self.file_path}::{self.symbol_name}"
    
    def to_document_text(self) -> str:
        """Converts symbol to text representation for semantic embedding."""
        text = f"Symbol: {self.symbol_name} ({self.symbol_type})\n"
        text += f"Signature: {self.signature}\n"
        text += f"Location: {self.source_id}:{self.file_path}#{self.source_span}\n"
        if self.docstring:
            text += f"Docstring:\n{self.docstring}\n"
        if self.calls:
            text += f"Calls: {', '.join(self.calls)}\n"
        if self.called_by:
            text += f"Called By: {', '.join(self.called_by)}\n"
        if self.tests:
            text += f"Tests: {', '.join(self.tests)}\n"
        return text

class ASTSymbolVisitor(ast.NodeVisitor):
    def __init__(self, source_id: str, file_path: str, source_code: str):
        self.source_id = source_id
        self.file_path = file_path
        self.source_code = source_code
        self.symbols: List[CodeSymbol] = []
        
        self.current_class = None
        
        # Track imports globally for the file
        self.imports = []
        
    def visit_Import(self, node):
        for alias in node.names:
            self.imports.append(alias.name)
        self.generic_visit(node)
        
    def visit_ImportFrom(self, node):
        module = node.module or ""
        for alias in node.names:
            self.imports.append(f"{module}.{alias.name}")
        self.generic_visit(node)

    def _get_signature(self, node) -> str:
        if isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef):
            args = [a.arg for a in node.args.args]
            return f"def {node.name}({', '.join(args)})"
        elif isinstance(node, ast.ClassDef):
            bases = [b.id for b in node.bases if isinstance(b, ast.Name)]
            base_str = f"({', '.join(bases)})" if bases else ""
            return f"class {node.name}{base_str}"
        return ""
        
    def _get_calls(self, node) -> List[str]:
        calls = []
        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                if isinstance(child.func, ast.Name):
                    calls.append(child.func.id)
                elif isinstance(child.func, ast.Attribute):
                    calls.append(child.func.attr)
        return list(set(calls))
        
    def visit_ClassDef(self, node):
        old_class = self.current_class
        self.current_class = node.name
        
        sym = CodeSymbol(
            source_id=self.source_id,
            file_path=self.file_path,
            symbol_name=node.name,
            symbol_type="class",
            signature=self._get_signature(node),
            docstring=ast.get_docstring(node),
            source_span=f"L{node.lineno}-L{node.end_lineno}",
            calls=self._get_calls(node),
            imports=self.imports
        )
        self.symbols.append(sym)
        self.generic_visit(node)
        self.current_class = old_class
        
    def visit_FunctionDef(self, node):
        self._visit_func(node)
        
    def visit_AsyncFunctionDef(self, node):
        self._visit_func(node)
        
    def _visit_func(self, node):
        name = f"{self.current_class}.{node.name}" if self.current_class else node.name
        sym = CodeSymbol(
            source_id=self.source_id,
            file_path=self.file_path,
            symbol_name=name,
            symbol_type="method" if self.current_class else "function",
            signature=self._get_signature(node),
            docstring=ast.get_docstring(node),
            source_span=f"L{node.lineno}-L{node.end_lineno}",
            calls=self._get_calls(node),
            imports=self.imports
        )
        self.symbols.append(sym)
        self.generic_visit(node)

def parse_python_file(source_id: str, file_path: str, source_code: str, version: str = "v1") -> List[CodeSymbol]:
    """Parses a Python file and extracts semantic CodeSymbols."""
    try:
        tree = ast.parse(source_code, filename=file_path)
    except SyntaxError:
        return []
        
    visitor = ASTSymbolVisitor(source_id, file_path, source_code)
    visitor.visit(tree)
    
    symbols = visitor.symbols
    for sym in symbols:
        sym.version = version
    return symbols

def parse_python_repo(source_id: str, repo_path: str, version: str = "v1") -> List[CodeSymbol]:
    """
    3-Stage Repository Parsing:
    1. Parse all files.
    2. Build symbol table.
    3. Resolve cross-file relations (calls, called_by, tests).
    """
    import os
    from pathlib import Path
    
    # Stage 1: Parse all files
    all_symbols = []
    repo_dir = Path(repo_path)
    for py_file in repo_dir.rglob("*.py"):
        try:
            rel_path = str(py_file.relative_to(repo_dir)).replace("\\", "/")
            with open(py_file, "r", encoding="utf-8") as f:
                source_code = f.read()
            symbols = parse_python_file(source_id, rel_path, source_code, version)
            all_symbols.extend(symbols)
        except Exception:
            pass
            
    # Stage 2: Build symbol table mapping unqualified names to their canonical IDs
    symbol_table: Dict[str, List[CodeSymbol]] = {}
    for sym in all_symbols:
        unqualified_name = sym.symbol_name.split('.')[-1]
        if unqualified_name not in symbol_table:
            symbol_table[unqualified_name] = []
        symbol_table[unqualified_name].append(sym)
        
    # Stage 3: Resolve cross-file relations
    for sym in all_symbols:
        new_calls = set()
        for call in sym.calls:
            if call in symbol_table:
                possible_targets = symbol_table[call]
                for target in possible_targets:
                    # Simple heuristic: if name matches, we consider it a call edge
                    # (in a real system, we'd check imports or scopes to handle collisions perfectly)
                    new_calls.add(target.canonical_id)
                    target.called_by.append(sym.canonical_id)
                    if sym.symbol_name.startswith("test_") or "test" in sym.file_path.lower():
                        target.tests.append(sym.canonical_id)
        sym.calls = list(new_calls)
        
    # Deduplicate
    for sym in all_symbols:
        sym.called_by = list(set(sym.called_by))
        sym.tests = list(set(sym.tests))
        
    return all_symbols
