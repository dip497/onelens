import React, { useState, useEffect, useRef } from 'react';
import { HttpAgent } from '@ag-ui/client';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Send, Bot, User } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkBreaks from 'remark-breaks';
import rehypeHighlight from 'rehype-highlight';

interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
}

interface AgentChatProps {
  agentUrl?: string;
  title?: string;
}

export function AgentChat({
  agentUrl = 'http://localhost:8000/agent',
  title = 'AI Assistant'
}: AgentChatProps) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [agent, setAgent] = useState<HttpAgent | null>(null);
  const scrollAreaRef = useRef<HTMLDivElement>(null);
  const currentAssistantMessageRef = useRef<Message | null>(null);

  useEffect(() => {
    // Initialize AG-UI HttpAgent - connects to AG-UI compatible backend
    const agentInstance = new HttpAgent({
      url: agentUrl,
    });
    setAgent(agentInstance);
  }, [agentUrl]);

  useEffect(() => {
    // Auto-scroll to bottom when new messages arrive
    if (scrollAreaRef.current) {
      scrollAreaRef.current.scrollTop = scrollAreaRef.current.scrollHeight;
    }
  }, [messages]);

  const sendMessage = async () => {
    if (!input.trim() || !agent || isLoading) return;

    const userMessage: Message = {
      id: Date.now().toString(),
      role: 'user',
      content: input.trim(),
      timestamp: new Date(),
    };

    setMessages(prev => [...prev, userMessage]);
    setInput('');
    setIsLoading(true);

    // Clear the current assistant message reference
    currentAssistantMessageRef.current = null;

    try {
      // Create a fresh agent instance or reset the existing one to avoid state accumulation
      const freshAgent = new HttpAgent({
        url: agentUrl,
      });

      // Set the complete conversation history including the new user message
      const allMessages = [...messages, userMessage];
      freshAgent.messages = allMessages.map(msg => ({
        id: msg.id,
        role: msg.role,
        content: msg.content,
      }));

      // Subscribe to agent events and run
      freshAgent.subscribe({
        onTextMessageStartEvent: ({ event }) => {
          // Only create new assistant message if we don't have one already
          if (!currentAssistantMessageRef.current) {
            const newAssistantMessage: Message = {
              id: event.messageId || `assistant-${Date.now()}`,
              role: 'assistant',
              content: '',
              timestamp: new Date(),
            };
            currentAssistantMessageRef.current = newAssistantMessage;
            setMessages(prev => [...prev, newAssistantMessage]);
          }
        },

        onTextMessageContentEvent: ({ event }) => {
          // Stream content to the current assistant message
          if (currentAssistantMessageRef.current) {
            const messageId = currentAssistantMessageRef.current.id;
            setMessages(prev =>
              prev.map(msg =>
                msg.id === messageId
                  ? { ...msg, content: msg.content + event.delta }
                  : msg
              )
            );
          }
        },

        onRunFinishedEvent: () => {
          setIsLoading(false);
          currentAssistantMessageRef.current = null;
        },

        onRunErrorEvent: ({ event }) => {
          console.error('Agent error:', event);
          setIsLoading(false);
          currentAssistantMessageRef.current = null;

          setMessages(prev => [...prev, {
            id: `error-${Date.now()}`,
            role: 'assistant',
            content: 'Sorry, I encountered an error. Please try again.',
            timestamp: new Date(),
          }]);
        },
      });

      // Run the agent
      await freshAgent.runAgent({
        tools: [], // Can add tools here for enhanced functionality
      });

    } catch (error) {
      console.error('Error sending message:', error);
      setIsLoading(false);
      currentAssistantMessageRef.current = null;

      setMessages(prev => [...prev, {
        id: `error-${Date.now()}`,
        role: 'assistant',
        content: 'Sorry, I encountered an error. Please try again.',
        timestamp: new Date(),
      }]);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  const clearConversation = () => {
    setMessages([]);
    currentAssistantMessageRef.current = null;
  };

  return (
    <Card className="w-full max-w-5xl mx-auto h-[700px] flex flex-col">
      <CardHeader className="flex-shrink-0 border-b">
        <CardTitle className="flex items-center gap-2 justify-between">
          <div className="flex items-center gap-2">
            <Bot className="h-5 w-5" />
            {title}
          </div>
          {/* <Button
            variant="outline"
            size="sm"
            onClick={clearConversation}
            disabled={isLoading}
          >
            Clear
          </Button> */}
        </CardTitle>
      </CardHeader>
      <CardContent className="flex-1 flex flex-col p-0 overflow-hidden">
        <div className="flex-1 overflow-y-auto p-4" ref={scrollAreaRef}>
          <div className="space-y-4 max-w-4xl mx-auto">
            {messages.length === 0 && (
              <div className="text-center text-muted-foreground py-8">
                Start a conversation with the AI assistant
              </div>
            )}
            {messages.map((message) => (
              <div
                key={message.id}
                className={`flex gap-3 ${message.role === 'user' ? 'justify-end' : 'justify-start'
                  }`}
              >
                <div
                  className={`flex gap-3 max-w-[85%] ${message.role === 'user' ? 'flex-row-reverse' : 'flex-row'
                    }`}
                >
                  <div className="flex-shrink-0">
                    {message.role === 'user' ? (
                      <div className="w-8 h-8 rounded-full bg-primary flex items-center justify-center">
                        <User className="h-4 w-4 text-primary-foreground" />
                      </div>
                    ) : (
                      <div className="w-8 h-8 rounded-full bg-muted flex items-center justify-center">
                        <Bot className="h-4 w-4" />
                      </div>
                    )}
                  </div>
                  <div
                    className={`rounded-lg px-4 py-3 ${message.role === 'user'
                      ? 'bg-primary text-primary-foreground'
                      : 'bg-muted'
                      }`}
                  >
                    {message.role === 'assistant' ? (
                      <div className="text-sm prose prose-sm dark:prose-invert max-w-none">
                        <ReactMarkdown
                          remarkPlugins={[remarkGfm, remarkBreaks]}
                          rehypePlugins={[rehypeHighlight]}
                          components={{
                            p: ({ children }) => <p className="mb-2 last:mb-0">{children}</p>,
                            ul: ({ children }) => <ul className="list-disc pl-4 mb-2">{children}</ul>,
                            ol: ({ children }) => <ol className="list-decimal pl-4 mb-2">{children}</ol>,
                            li: ({ children }) => <li className="mb-1">{children}</li>,
                            code: ({ node, className, children, ...props }) => {
                              const match = /language-(\w+)/.exec(className || '');
                              const inline = !match;
                              return inline ? (
                                <code className="px-1 py-0.5 rounded bg-black/10 dark:bg-white/10 text-xs" {...props}>
                                  {children}
                                </code>
                              ) : (
                                <pre className="overflow-x-auto p-3 rounded bg-black/5 dark:bg-white/5 mb-2">
                                  <code className={className} {...props}>{children}</code>
                                </pre>
                              );
                            },
                          blockquote: ({ children }) => (
                            <blockquote className="border-l-4 border-gray-300 pl-3 italic">
                              {children}
                            </blockquote>
                          ),
                          h1: ({ children }) => <h1 className="text-lg font-bold mb-2">{children}</h1>,
                          h2: ({ children }) => <h2 className="text-base font-bold mb-2">{children}</h2>,
                          h3: ({ children }) => <h3 className="text-sm font-bold mb-2">{children}</h3>,
                          a: ({ href, children }) => (
                            <a href={href} className="text-blue-500 hover:underline" target="_blank" rel="noopener noreferrer">
                              {children}
                            </a>
                          ),
                          table: ({ children }) => (
                            <div className="overflow-x-auto mb-2">
                              <table className="min-w-full divide-y divide-gray-200">{children}</table>
                            </div>
                          ),
                          thead: ({ children }) => <thead className="bg-gray-50 dark:bg-gray-800">{children}</thead>,
                          tbody: ({ children }) => <tbody className="divide-y divide-gray-200">{children}</tbody>,
                          tr: ({ children }) => <tr>{children}</tr>,
                          th: ({ children }) => (
                            <th className="px-3 py-2 text-left text-xs font-medium uppercase tracking-wider">
                              {children}
                            </th>
                          ),
                          td: ({ children }) => <td className="px-3 py-2 text-sm">{children}</td>,
                        }}
                      >
                        {message.content}
                      </ReactMarkdown>
                      </div>
                    ) : (
                      <p className="text-sm whitespace-pre-wrap break-words">{message.content}</p>
                    )}
                    <p className="text-xs opacity-70 mt-2">
                      {message.timestamp.toLocaleTimeString()}
                    </p>
                  </div>
                </div>
              </div>
            ))}
            {isLoading && (
              <div className="flex gap-3 justify-start">
                <div className="flex gap-3">
                  <div className="w-8 h-8 rounded-full bg-muted flex items-center justify-center">
                    <Bot className="h-4 w-4" />
                  </div>
                  <div className="bg-muted rounded-lg px-4 py-3">
                    <div className="flex gap-1">
                      <div className="w-2 h-2 bg-current rounded-full animate-bounce" />
                      <div className="w-2 h-2 bg-current rounded-full animate-bounce" style={{ animationDelay: '0.1s' }} />
                      <div className="w-2 h-2 bg-current rounded-full animate-bounce" style={{ animationDelay: '0.2s' }} />
                    </div>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
        <div className="flex-shrink-0 border-t p-4 bg-background">
          <div className="flex gap-2 max-w-4xl mx-auto">
            <Input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Type your message..."
              disabled={isLoading}
              className="flex-1"
            />
            <Button
              onClick={sendMessage}
              disabled={!input.trim() || isLoading}
              size="icon"
            >
              <Send className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}