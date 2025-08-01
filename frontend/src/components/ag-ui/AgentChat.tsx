import React, { useState, useEffect, useRef } from 'react';
import { HttpAgent } from '@ag-ui/client';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Send, Bot, User } from 'lucide-react';

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

    // Set up event handlers ONCE when agent is created
    agentInstance.subscribe({
      onTextMessageStartEvent: ({ event }) => {
        // Create new assistant message when text starts
        const newAssistantMessage: Message = {
          id: event.messageId || Date.now().toString(),
          role: 'assistant',
          content: '',
          timestamp: new Date(),
        };

        currentAssistantMessageRef.current = newAssistantMessage;
        setMessages(prev => [...prev, newAssistantMessage]);
      },

      onTextMessageContentEvent: ({ event }) => {
        // Stream content to the current assistant message
        if (currentAssistantMessageRef.current && event.messageId === currentAssistantMessageRef.current.id) {
          setMessages(prev =>
            prev.map(msg =>
              msg.id === event.messageId
                ? { ...msg, content: msg.content + event.delta }
                : msg
            )
          );
        }
      },

      onTextMessageEndEvent: ({ event }) => {
        // Message is complete, clear the reference
        if (currentAssistantMessageRef.current?.id === event.messageId) {
          currentAssistantMessageRef.current = null;
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
          id: Date.now().toString(),
          role: 'assistant',
          content: 'Sorry, I encountered an error. Please try again.',
          timestamp: new Date(),
        }]);
      },
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

    try {
      // Clear the current assistant message reference for new conversation turn
      currentAssistantMessageRef.current = null;

      // Add user message to agent's message history
      agent.messages = [
        ...agent.messages,
        {
          id: userMessage.id,
          role: 'user',
          content: userMessage.content,
        },
      ];

      // Run the agent - event handlers are already set up in useEffect
      await agent.runAgent({
        tools: [], // Can add tools here for enhanced functionality
      });

    } catch (error) {
      console.error('Error sending message:', error);
      setIsLoading(false);
      currentAssistantMessageRef.current = null;
      setMessages(prev => [...prev, {
        id: Date.now().toString(),
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

  return (
    <Card className="w-full max-w-2xl mx-auto h-[600px] flex flex-col">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Bot className="h-5 w-5" />
          {title}
        </CardTitle>
      </CardHeader>
      <CardContent className="flex-1 flex flex-col gap-4">
        <ScrollArea className="flex-1 pr-4" ref={scrollAreaRef}>
          <div className="space-y-4">
            {messages.length === 0 && (
              <div className="text-center text-muted-foreground py-8">
                Start a conversation with the AI assistant
              </div>
            )}
            {messages.map((message) => (
              <div
                key={message.id}
                className={`flex gap-3 ${
                  message.role === 'user' ? 'justify-end' : 'justify-start'
                }`}
              >
                <div
                  className={`flex gap-2 max-w-[80%] ${
                    message.role === 'user' ? 'flex-row-reverse' : 'flex-row'
                  }`}
                >
                  <div className="flex-shrink-0">
                    {message.role === 'user' ? (
                      <User className="h-6 w-6 mt-1" />
                    ) : (
                      <Bot className="h-6 w-6 mt-1" />
                    )}
                  </div>
                  <div
                    className={`rounded-lg px-3 py-2 ${
                      message.role === 'user'
                        ? 'bg-primary text-primary-foreground'
                        : 'bg-muted'
                    }`}
                  >
                    <p className="text-sm whitespace-pre-wrap">{message.content}</p>
                    <p className="text-xs opacity-70 mt-1">
                      {message.timestamp.toLocaleTimeString()}
                    </p>
                  </div>
                </div>
              </div>
            ))}
            {isLoading && (
              <div className="flex gap-3 justify-start">
                <div className="flex gap-2">
                  <Bot className="h-6 w-6 mt-1" />
                  <div className="bg-muted rounded-lg px-3 py-2">
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
        </ScrollArea>
        <div className="flex gap-2">
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
      </CardContent>
    </Card>
  );
}
