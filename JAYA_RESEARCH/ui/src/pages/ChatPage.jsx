import { useState } from 'react';
import { Send, Paperclip, Bot, User, Search } from 'lucide-react';
import clsx from 'clsx';
import { motion } from 'framer-motion';
import api from '../services/api';

export default function ChatPage() {
    const [messages, setMessages] = useState([
        { role: 'assistant', content: 'Hello! I am your AI Research Assistant. You can ask me questions, or upload documents to analyze.' }
    ]);
    const [input, setInput] = useState('');
    const [sources, setSources] = useState([]);

    const handleUrlSubmit = async () => {
        const url = prompt("Enter YouTube or Article URL:");
        if (!url) return;

        setMessages(prev => [...prev, {
            role: 'assistant',
            content: `Started analyzing video: ${url}...`,
            isThinking: true
        }]);

        try {
            await api.researchApi.ingestVideo(url);
            setSources(prev => [...prev, { title: 'New Video Source', type: 'video', url }]);
            setMessages(prev => [...prev, {
                role: 'assistant',
                content: "Video analysis completed! Visuals and audio have been indexed. You can now ask questions about it."
            }]);
        } catch (e) {
            setMessages(prev => [...prev, {
                role: 'assistant',
                content: `Error analyzing video: ${e.message}`
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
            const res = await api.chat(input, [], workspaceId);
            const botMsg = { role: 'assistant', content: res.answer };
            setMessages(prev => [...prev, botMsg]);
        } catch (err) {
            console.error(err);
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="flex h-full">
            {/* Sources Panel */}
            <div className="w-80 border-r border-[var(--border)] p-4 bg-black/10 hidden lg:block">
                <h2 className="text-sm font-semibold mb-4 text-gray-400 uppercase tracking-wider">Sources & Context</h2>

                <div className="space-y-3">
                    <button className="w-full flex items-center gap-2 px-3 py-2 bg-white/5 hover:bg-white/10 rounded-lg text-sm transition-colors border border-white/5 hover:border-white/10">
                        <Paperclip size={14} />
                        <span>Upload PDF/Doc</span>
                    </button>

                    <button
                        onClick={handleUrlSubmit}
                        className="w-full flex items-center gap-2 px-3 py-2 bg-white/5 hover:bg-white/10 rounded-lg text-sm transition-colors border border-white/5 hover:border-white/10"
                    >
                        <LinkIcon size={14} />
                        <span>Add URL / Youtube</span>
                    </button>
                </div>

                <div className="mt-6">
                    <h3 className="text-xs font-medium text-gray-500 mb-2">Active Sources</h3>
                    <div className="space-y-2">
                        {/* Mock Source */}
                        <div className="p-2 rounded bg-white/5 text-xs text-gray-300 flex items-center gap-2">
                            <div className="w-1 h-8 bg-blue-500 rounded-full" />
                            <div>
                                <div className="font-medium truncate">Football Manager Guide 2024.pdf</div>
                                <div className="text-[10px] text-gray-500">12 chunks • 85% relevance</div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            {/* Chat Area */}
            <div className="flex-1 flex flex-col relative">
                <div className="flex-1 overflow-y-auto p-6 space-y-6">
                    {messages.map((msg, i) => (
                        <motion.div
                            initial={{ opacity: 0, y: 10 }}
                            animate={{ opacity: 1, y: 0 }}
                            key={i}
                            className={clsx(
                                "flex gap-4 max-w-3xl mx-auto",
                                msg.role === 'user' ? "flex-row-reverse" : ""
                            )}
                        >
                            <div className={clsx(
                                "w-8 h-8 rounded-full flex items-center justify-center shrink-0",
                                msg.role === 'assistant' ? "bg-primary/20 text-primary" : "bg-gray-700"
                            )}>
                                {msg.role === 'assistant' ? <Bot size={18} /> : <User size={18} />}
                            </div>

                            <div className={clsx(
                                "px-4 py-3 rounded-2xl max-w-[80%] text-sm leading-relaxed",
                                msg.role === 'assistant' ? "bg-white/5 text-gray-200" : "bg-primary text-white"
                            )}>
                                {msg.content}
                                {msg.isThinking && (
                                    <div className="flex gap-1 mt-2">
                                        <span className="w-1.5 h-1.5 bg-current rounded-full animate-bounce" />
                                        <span className="w-1.5 h-1.5 bg-current rounded-full animate-bounce delay-100" />
                                        <span className="w-1.5 h-1.5 bg-current rounded-full animate-bounce delay-200" />
                                    </div>
                                )}
                            </div>
                        </motion.div>
                    ))}
                </div>

                {/* Input Area */}
                <div className="p-4 border-t border-[var(--border)] bg-black/20 backdrop-blur-sm">
                    <div className="max-w-3xl mx-auto relative">
                        <input
                            type="text"
                            value={input}
                            onChange={(e) => setInput(e.target.value)}
                            onKeyDown={(e) => e.key === 'Enter' && handleSend()}
                            placeholder="Ask about your documents or start a new research..."
                            className="w-full bg-[var(--bg-card)] border border-[var(--border)] rounded-xl pl-4 pr-12 py-3 focus:outline-none focus:ring-2 focus:ring-primary/50 placeholder:text-gray-600 shadow-lg"
                        />
                        <button
                            onClick={handleSend}
                            className="absolute right-2 top-2 p-1.5 bg-primary hover:bg-primary-hover rounded-lg text-white transition-colors"
                        >
                            <Send size={16} />
                        </button>
                    </div>
                    <div className="text-center mt-2">
                        <span className="text-[10px] text-gray-600">AI-Q Research Model v2.0 • Powered by NVIDIA NIM</span>
                    </div>
                </div>
            </div>
        </div>
    );
}

const LinkIcon = ({ size }) => (
    <svg xmlns="http://www.w3.org/2000/svg" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71" /><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71" /></svg>
)
