import { useState, useEffect, useRef } from 'react';
import { Send, Plus, Sparkles, Brain, ChevronDown, ChevronRight, Youtube, FileText, Upload, Download, Trash2 } from 'lucide-react';
import clsx from 'clsx';
import { motion, AnimatePresence } from 'framer-motion';
import api from '../services/api';
import ReactMarkdown from 'react-markdown';
import rehypeHighlight from 'rehype-highlight';
import 'highlight.js/styles/atom-one-dark.css';

// Helper to parse <think> content
const parseMessageContent = (content) => {
    const thinkRegex = /<think>([\s\S]*?)<\/think>/;
    const match = content.match(thinkRegex);

    if (match) {
        return {
            thinking: match[1].trim(),
            answer: content.replace(match[0], '').trim()
        };
    }
    return { thinking: null, answer: content };
};

export default function ChatPage({ workspaceId }) {
    // Load initial state from local storage or default
    const [messages, setMessages] = useState(() => {
        const saved = localStorage.getItem(`JAYA_CHAT_${workspaceId}`);
        return saved ? JSON.parse(saved) : [
            { role: 'assistant', content: 'Hello! I am JAYA, your research companion. I can analyze documents, videos, or help you brainstorm. What are we working on today?' }
        ];
    });

    const [input, setInput] = useState('');
    const [sources, setSources] = useState([]); 
    const [isLoading, setLoading] = useState(false);
    const [workspaceDocs, setWorkspaceDocs] = useState([]);
    const [previewFile, setPreviewFile] = useState(null);
    const messagesEndRef = useRef(null);

    // Save messages whenever they change
    useEffect(() => {
        localStorage.setItem(`JAYA_CHAT_${workspaceId}`, JSON.stringify(messages));
    }, [messages, workspaceId]);

    // Load messages and workspace docs when workspaceId changes
    useEffect(() => {
        const saved = localStorage.getItem(`JAYA_CHAT_${workspaceId}`);
        if (saved) {
            setMessages(JSON.parse(saved));
        } else {
            setMessages([{ role: 'assistant', content: 'Hello! I am JAYA, your research companion. I can analyze documents, videos, or help you brainstorm. What are we working on today?' }]);
        }
        loadWorkspaceDocs();
    }, [workspaceId]);

    const loadWorkspaceDocs = async () => {
        try {
            const data = await api.listDocuments(workspaceId || 'default');
            setWorkspaceDocs(data);
        } catch (e) {
            console.error("Failed to load workspace documents", e);
        }
    };

    const scrollToBottom = () => {
        messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
    };

    useEffect(() => {
        scrollToBottom();
    }, [messages]);

    const handleUrlSubmit = async () => {
        const url = prompt("Enter YouTube or Article URL:");
        if (!url) return;

        setMessages(prev => [...prev, {
            role: 'assistant',
            content: `Analyzing source: ${url}...`,
            isThinking: true
        }]);

        try {
            await api.ingestVideo(url);
            setSources(prev => [...prev, { title: 'New Video Source', type: 'video', url }]);
            setMessages(prev => prev.map((msg, i) =>
                i === prev.length - 1 ? { role: 'assistant', content: "Source analyzed and added to knowledge graph." } : msg
            ));
        } catch (e) {
            setMessages(prev => [...prev, {
                role: 'assistant',
                content: `Error analyzing source: ${e.message}`
            }]);
        }
    };

    const handleSend = async () => {
        if (!input.trim()) return;

        const userMsg = { role: 'user', content: input };
        setMessages(prev => [...prev, userMsg]);
        setInput('');
        setLoading(true);

        try {
            // Simulate "thinking" state
            setMessages(prev => [...prev, { role: 'assistant', content: '', isThinking: true }]);

            const res = await api.chat(input, [], workspaceId || 'default');

            // Remove thinking message and add real response
            setMessages(prev => {
                const newHistory = prev.filter(m => !m.isThinking);
                return [...newHistory, { role: 'assistant', content: res.answer }];
            });

            // Reload workspace documents since JAYA might have generated a file
            await loadWorkspaceDocs();

        } catch (err) {
            console.error(err);
            setMessages(prev => prev.filter(m => !m.isThinking).concat({ role: 'assistant', content: "I encountered an error connecting to the neural core." }));
        } finally {
            setLoading(false);
        }
    };

    const handleFileClick = async (doc) => {
        try {
            const url = api.viewDocumentUrl(workspaceId || 'default', doc.name);
            const res = await fetch(url);
            if (!res.ok) throw new Error("Could not retrieve file content.");
            const content = await res.text();
            setPreviewFile({
                name: doc.name,
                content: content,
                type: doc.type
            });
        } catch (e) {
            alert(`Error opening file: ${e.message}`);
        }
    };

    const handleFileDelete = async (filename, e) => {
        e.stopPropagation();
        if (!confirm(`Are you sure you want to delete '${filename}'?`)) return;
        try {
            await api.deleteDocument(workspaceId || 'default', filename);
            await loadWorkspaceDocs();
            if (previewFile?.name === filename) {
                setPreviewFile(null);
            }
        } catch (e) {
            alert(`Delete failed: ${e.message}`);
        }
    };

    const handleFileUpload = async (e) => {
        const file = e.target.files?.[0];
        if (!file) return;

        try {
            await api.uploadDocumentToWorkspace(file, workspaceId || 'default');
            await loadWorkspaceDocs();
        } catch (e) {
            alert(`Upload failed: ${e.message}`);
        }
    };

    const docInputRef = useRef(null);

    const handleRAGUpload = async (e) => {
        const file = e.target.files?.[0];
        if (!file) return;

        setMessages(prev => [...prev, {
            role: 'assistant',
            content: `Uploading and ingesting: ${file.name}...`,
            isThinking: true
        }]);

        try {
            await api.uploadThesis(file, workspaceId || 'default');
            setSources(prev => [...prev, { title: file.name, type: 'pdf', url: '#' }]);
            setMessages(prev => prev.map((msg, i) =>
                i === prev.length - 1 ? { role: 'assistant', content: `Document '${file.name}' has been successfully ingested into the RAG context.` } : msg
            ));
        } catch (err) {
            setMessages(prev => prev.map((msg, i) =>
                i === prev.length - 1 ? { role: 'assistant', content: `Failed to ingest document: ${err.message}` } : msg
            ));
        }
    };


    // Component for rendering thinking block
    const ThinkingBlock = ({ content }) => {
        const [isOpen, setIsOpen] = useState(false);
        if (!content) return null;

        return (
            <div className="mb-3">
                <button
                    onClick={() => setIsOpen(!isOpen)}
                    className="flex items-center gap-2 text-xs font-medium text-notebook-text-secondary hover:text-notebook-text-accent transition-colors mb-2 bg-notebook-card px-3 py-1.5 rounded-lg border border-notebook-border w-fit"
                >
                    <Brain size={14} className={clsx(isOpen ? "text-notebook-text-accent" : "text-notebook-text-secondary")} />
                    <span>Thinking Process</span>
                    {isOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                </button>

                <AnimatePresence>
                    {isOpen && (
                        <motion.div
                            initial={{ height: 0, opacity: 0 }}
                            animate={{ height: "auto", opacity: 1 }}
                            exit={{ height: 0, opacity: 0 }}
                            className="overflow-hidden"
                        >
                            <div className="pl-4 border-l-2 border-notebook-border ml-2 my-2 py-2">
                                <div className="text-sm font-mono text-notebook-text-secondary whitespace-pre-wrap bg-notebook-bg/50 p-3 rounded-lg border border-notebook-border/50 overflow-x-auto">
                                    <ReactMarkdown rehypePlugins={[rehypeHighlight]}>{content}</ReactMarkdown>
                                </div>
                            </div>
                        </motion.div>
                    )}
                </AnimatePresence>
            </div>
        );
    };

    return (
        <div className="flex h-full bg-notebook-bg text-notebook-text-primary overflow-hidden relative">
            {/* Sources Panel (Left) */}
            <div className="w-[300px] bg-notebook-sidebar border-r border-notebook-border p-5 hidden lg:flex flex-col shrink-0">
                <div className="flex items-center justify-between mb-6">
                    <h2 className="text-sm font-semibold text-notebook-text-secondary uppercase tracking-wider">Sources</h2>
                    <button className="p-1 hover:bg-notebook-hover rounded text-notebook-text-secondary">
                        <Plus size={16} />
                    </button>
                </div>

                <div className="space-y-3 mb-6">
                    <input
                        type="file"
                        ref={docInputRef}
                        onChange={handleRAGUpload}
                        className="hidden"
                        accept=".pdf,.txt,.md"
                    />
                    <button
                        onClick={() => docInputRef.current?.click()}
                        className="w-full flex items-center gap-3 px-4 py-3 bg-[#2a2d35] hover:bg-[#33363f] rounded-xl text-sm transition-all border border-notebook-border hover:border-notebook-text-accent/30 group shadow-sm"
                    >
                        <div className="w-8 h-8 rounded-full bg-blue-500/20 flex items-center justify-center text-blue-400 group-hover:scale-110 transition-transform">
                            <FileText size={16} />
                        </div>
                        <span className="font-medium text-notebook-text-primary">Upload Document</span>
                    </button>

                    <button
                        onClick={handleUrlSubmit}
                        className="w-full flex items-center gap-3 px-4 py-3 bg-[#2a2d35] hover:bg-[#33363f] rounded-xl text-sm transition-all border border-notebook-border hover:border-notebook-text-accent/30 group shadow-sm"
                    >
                        <div className="w-8 h-8 rounded-full bg-red-500/20 flex items-center justify-center text-red-400 group-hover:scale-110 transition-transform">
                            <Youtube size={16} />
                        </div>
                        <span className="font-medium text-notebook-text-primary">Add Link / Video</span>
                    </button>
                </div>

                <div className="flex-1 overflow-y-auto">
                    <h3 className="text-xs font-semibold text-notebook-text-secondary mb-3 uppercase tracking-wider">Active Context</h3>
                    <div className="space-y-2">
                        {sources.length === 0 && (
                            <div className="text-sm text-notebook-text-secondary italic px-2">No sources added yet.</div>
                        )}
                        <div className="p-3 rounded-lg bg-white/5 border border-white/5 hover:border-notebook-text-accent/50 transition-colors cursor-pointer group">
                            <div className="flex items-start gap-3">
                                <div className="mt-1 w-1.5 h-1.5 rounded-full bg-green-400 shadow-[0_0_8px_rgba(74,222,128,0.5)]" />
                                <div>
                                    <div className="text-sm font-medium text-notebook-text-primary group-hover:text-notebook-text-accent transition-colors">Project JAYA Architecture.pdf</div>
                                    <div className="text-xs text-notebook-text-secondary mt-1">Added today • PDF</div>
                                </div>
                            </div>
                        </div>
                        {sources.map((src, i) => (
                            <div key={i} className="p-3 rounded-lg bg-white/5 border border-white/5 hover:border-notebook-text-accent/50 transition-colors cursor-pointer group">
                                <div className="flex items-start gap-3">
                                    <div className="mt-1 w-1.5 h-1.5 rounded-full bg-blue-400" />
                                    <div>
                                        <div className="text-sm font-medium text-notebook-text-primary group-hover:text-notebook-text-accent transition-colors truncate w-48">{src.title}</div>
                                        <div className="text-xs text-notebook-text-secondary mt-1 capitalize">{src.type}</div>
                                    </div>
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            </div>

            {/* Main Chat Area (Center) */}
            <div className="flex-1 flex flex-col relative h-full overflow-hidden">
                <div className="absolute top-0 left-0 right-0 h-16 bg-gradient-to-b from-notebook-bg to-transparent z-10 pointer-events-none" />

                <div className="flex-1 overflow-y-auto p-4 md:p-8 space-y-8 scroll-smooth">
                    {messages.map((msg, i) => {
                        const { thinking, answer } = msg.role === 'assistant' && !msg.isThinking
                            ? parseMessageContent(msg.content)
                            : { thinking: null, answer: msg.content };

                        return (
                            <motion.div
                                initial={{ opacity: 0, y: 10 }}
                                animate={{ opacity: 1, y: 0 }}
                                key={i}
                                className={clsx(
                                    "flex gap-4 max-w-4xl mx-auto",
                                    msg.role === 'user' ? "flex-row-reverse" : ""
                                )}
                            >
                                {/* Avatar */}
                                {msg.role === 'assistant' && (
                                    <div className="w-8 h-8 rounded-full bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center shrink-0 shadow-glow mt-1">
                                        <Sparkles size={14} className="text-white" />
                                    </div>
                                )}

                                {/* Message Content */}
                                <div className={clsx(
                                    "flex flex-col max-w-[85%]",
                                    msg.role === 'user' ? "items-end" : "items-start w-full"
                                )}>
                                    {/* Thinking Block */}
                                    {thinking && <ThinkingBlock content={thinking} />}

                                    <div className={clsx(
                                        "px-5 py-3.5 text-[0.95rem] leading-relaxed shadow-sm w-fit",
                                        msg.role === 'user'
                                            ? "bg-[#282a2f] text-notebook-text-primary rounded-2xl rounded-tr-sm border border-notebook-border"
                                            : "text-notebook-text-primary markdown-body" 
                                    )}>
                                        {msg.role === 'user' ? (
                                            answer
                                        ) : (
                                            <div className="prose prose-invert prose-p:leading-relaxed prose-pre:bg-[#1e1e1e] prose-pre:border prose-pre:border-gray-800 max-w-none">
                                                <ReactMarkdown rehypePlugins={[rehypeHighlight]}>
                                                    {answer}
                                                </ReactMarkdown>
                                            </div>
                                        )}

                                        {msg.isThinking && (
                                            <div className="flex items-center gap-2 text-notebook-text-accent">
                                                <span className="w-1.5 h-1.5 bg-current rounded-full animate-bounce" />
                                                <span className="w-1.5 h-1.5 bg-current rounded-full animate-bounce delay-100" />
                                                <span className="w-1.5 h-1.5 bg-current rounded-full animate-bounce delay-200" />
                                                <span className="text-sm ml-2 font-medium">Thinking...</span>
                                            </div>
                                        )}
                                    </div>
                                </div>
                            </motion.div>
                        );
                    })}
                    <div ref={messagesEndRef} />
                </div>

                {/* Input Area */}
                <div className="p-6 shrink-0">
                    <div className="max-w-4xl mx-auto relative group">
                        <div className="absolute -inset-0.5 bg-gradient-to-r from-blue-500 to-purple-600 rounded-2xl opacity-20 group-hover:opacity-40 transition-opacity blur duration-500" />
                        <div className="relative bg-notebook-card rounded-2xl flex items-center pr-3 border border-notebook-border shadow-2xl">
                            <button className="p-4 text-notebook-text-secondary hover:text-notebook-text-primary transition-colors">
                                <Plus size={20} />
                            </button>
                            <input
                                type="text"
                                value={input}
                                onChange={(e) => setInput(e.target.value)}
                                onKeyDown={(e) => e.key === 'Enter' && handleSend()}
                                placeholder="Ask JAYA to write outline, draft reports, scripts, or ask questions..."
                                className="flex-1 bg-transparent border-none focus:ring-0 text-notebook-text-primary placeholder:text-notebook-text-secondary/50 py-4 text-base"
                                autoFocus
                            />
                            <button
                                onClick={handleSend}
                                disabled={!input.trim()}
                                className="p-2.5 bg-notebook-text-primary hover:bg-white rounded-xl text-notebook-bg transition-all disabled:opacity-50 disabled:cursor-not-allowed transform active:scale-95"
                            >
                                <Send size={18} fill="currentColor" />
                            </button>
                        </div>
                        <div className="text-center mt-3 text-xs text-notebook-text-secondary font-medium tracking-wide">
                            JAYA v2.0 • Powered by NVIDIA NIM • File Manager Tool Active
                        </div>
                    </div>
                </div>
            </div>

            {/* Workspace Files Panel (Right) */}
            <div className="w-[300px] bg-notebook-sidebar border-l border-notebook-border p-5 hidden xl:flex flex-col shrink-0">
                <div className="flex items-center justify-between mb-6">
                    <h2 className="text-sm font-semibold text-notebook-text-secondary uppercase tracking-wider">Workspace Files</h2>
                    <label className="p-1.5 hover:bg-notebook-hover rounded text-notebook-text-secondary cursor-pointer hover:text-notebook-text-accent transition-colors" title="Upload Document to Workspace">
                        <Upload size={16} />
                        <input
                            type="file"
                            onChange={handleFileUpload}
                            className="hidden"
                        />
                    </label>
                </div>

                <div className="flex-1 overflow-y-auto space-y-2">
                    {workspaceDocs.length === 0 ? (
                        <div className="text-sm text-notebook-text-secondary italic px-2 pt-4">
                            No generated files yet. Ask JAYA to create a file!
                        </div>
                    ) : (
                        workspaceDocs.map((doc, idx) => (
                            <div
                                key={idx}
                                onClick={() => handleFileClick(doc)}
                                className="p-3 rounded-lg bg-white/5 border border-white/5 hover:border-notebook-text-accent/50 hover:bg-white/[0.08] transition-all cursor-pointer group flex items-center justify-between"
                            >
                                <div className="flex items-center gap-3 overflow-hidden">
                                    <div className="text-notebook-text-accent shrink-0">
                                        <FileText size={16} />
                                    </div>
                                    <div className="overflow-hidden">
                                        <div className="text-sm font-medium text-notebook-text-primary truncate">{doc.name}</div>
                                        <div className="text-[10px] text-notebook-text-secondary mt-0.5">
                                            {(doc.size / 1024).toFixed(1)} KB • {doc.type.toUpperCase()}
                                        </div>
                                    </div>
                                </div>
                                <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity ml-2 shrink-0">
                                    <a
                                        href={api.viewDocumentUrl(workspaceId || 'default', doc.name)}
                                        download={doc.name}
                                        onClick={(e) => e.stopPropagation()}
                                        className="p-1 hover:bg-[#343842] rounded text-notebook-text-secondary hover:text-notebook-text-accent transition-colors"
                                        title="Download"
                                    >
                                        <Download size={14} />
                                    </a>
                                    <button
                                        onClick={(e) => handleFileDelete(doc.name, e)}
                                        className="p-1 hover:bg-[#343842] rounded text-notebook-text-secondary hover:text-red-400 transition-colors"
                                        title="Delete"
                                    >
                                        <Trash2 size={14} />
                                    </button>
                                </div>
                            </div>
                        ))
                    )}
                </div>
            </div>

            {/* Document Preview Modal */}
            <AnimatePresence>
                {previewFile && (
                    <motion.div
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        exit={{ opacity: 0 }}
                        className="fixed inset-0 bg-black/70 backdrop-blur-sm z-50 flex items-center justify-center p-6 md:p-12"
                    >
                        <motion.div
                            initial={{ scale: 0.95, y: 20 }}
                            animate={{ scale: 1, y: 0 }}
                            exit={{ scale: 0.95, y: 20 }}
                            className="bg-notebook-bg border border-notebook-border rounded-2xl w-full max-w-5xl h-[85vh] flex flex-col overflow-hidden shadow-2xl"
                        >
                            {/* Modal Header */}
                            <div className="px-6 py-4 border-b border-notebook-border flex items-center justify-between bg-notebook-sidebar">
                                <div className="flex items-center gap-3">
                                    <FileText className="text-notebook-text-accent" size={18} />
                                    <span className="font-semibold text-notebook-text-primary">{previewFile.name}</span>
                                </div>
                                <div className="flex items-center gap-3">
                                    <a
                                        href={api.viewDocumentUrl(workspaceId || 'default', previewFile.name)}
                                        download={previewFile.name}
                                        className="px-3 py-1.5 bg-[#2a2d35] hover:bg-[#33363f] border border-notebook-border text-notebook-text-primary rounded-lg text-xs font-medium flex items-center gap-1.5 transition-all"
                                    >
                                        <Download size={12} />
                                        Download
                                    </a>
                                    <button
                                        onClick={() => setPreviewFile(null)}
                                        className="p-1 text-notebook-text-secondary hover:text-notebook-text-primary transition-colors text-lg"
                                    >
                                        ✕
                                    </button>
                                </div>
                            </div>

                            {/* Modal Content */}
                            <div className="flex-1 overflow-y-auto p-6 md:p-10 bg-notebook-bg/50">
                                <div className="max-w-4xl mx-auto prose prose-invert prose-p:leading-relaxed prose-pre:bg-[#1e1e1e] prose-pre:border prose-pre:border-gray-800 markdown-body">
                                    {previewFile.type === 'md' ? (
                                        <ReactMarkdown rehypePlugins={[rehypeHighlight]}>
                                            {previewFile.content}
                                        </ReactMarkdown>
                                    ) : (
                                        <pre className="text-sm font-mono text-notebook-text-primary whitespace-pre-wrap bg-[#1e1e1e] p-6 rounded-xl border border-notebook-border overflow-x-auto">
                                            {previewFile.content}
                                        </pre>
                                    )}
                                </div>
                            </div>
                        </motion.div>
                    </motion.div>
                )}
            </AnimatePresence>
        </div>
    );
}
