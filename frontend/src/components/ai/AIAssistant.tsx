import { useState, useRef, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Drawer, DrawerContent } from "@/components/ui/drawer"; // If not available, I can give a custom drawer
import {
  MessageCircle,
  Send,
  UploadCloud,
  Sparkles,
  X
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

interface Message {
  id: string;
  type: 'user' | 'ai' | 'system';
  content: string;
  timestamp: Date;
  actions?: Array<{
    label: string;
    action: () => void;
  }>;
}

export function AIAssistant() {
  const [isOpen, setIsOpen] = useState(false);
  const [messages, setMessages] = useState<Message[]>([
    {
      id: '1',
      type: 'ai',
      content:
        "Hi! I’m your OneLens assistant. Ask me anything about ITSM features, upload RFPs, or get competitive insights.",
      timestamp: new Date(),
      actions: [
        {
          label: 'Upload RFP',
          action: () => document.getElementById('file-input')?.click(),
        },
        {
          label: 'Compare Features',
          action: () => console.log('Compare features'),
        },
      ],
    },
  ]);
  const [inputValue, setInputValue] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const handleSendMessage = () => {
    if (!inputValue.trim()) return;

    const userMessage: Message = {
      id: Date.now().toString(),
      type: 'user',
      content: inputValue,
      timestamp: new Date(),
    };

    setMessages((prev) => [...prev, userMessage]);
    setInputValue('');
    setIsTyping(true);

    setTimeout(() => {
      const aiReply: Message = {
        id: (Date.now() + 1).toString(),
        type: 'ai',
        content: generateAIResponse(inputValue),
        timestamp: new Date(),
        actions: getContextualActions(inputValue),
      };
      setMessages((prev) => [...prev, aiReply]);
      setIsTyping(false);
    }, 1000);
  };

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    const systemMsg: Message = {
      id: Date.now().toString(),
      type: 'system',
      content: `📄 File received: ${file.name}. Parsing...`,
      timestamp: new Date(),
    };
    setMessages((prev) => [...prev, systemMsg]);

    setIsTyping(true);
    setTimeout(() => {
      const aiReply: Message = {
        id: (Date.now() + 1).toString(),
        type: 'ai',
        content: `The RFP **${file.name}** includes ITSM module requests like incident tracking, SLA compliance, and CMDB. Do you want a battle card, a compliance report, or proposal draft?`,
        timestamp: new Date(),
        actions: [
          { label: 'Generate Battle Card', action: () => console.log('battle card') },
          { label: 'Draft Proposal', action: () => console.log('draft proposal') },
        ],
      };
      setMessages((prev) => [...prev, aiReply]);
      setIsTyping(false);
    }, 2000);
  };

  const generateAIResponse = (input: string) => {
    const lower = input.toLowerCase();
    if (lower.includes("feature")) {
      return "Which ITSM feature would you like to explore? I can compare SLA enforcement, incident flows, or integrations.";
    }
    if (lower.includes("battle card")) {
      return "Tell me which competitor you're interested in: ServiceNow, Freshservice, or Zendesk?";
    }
    return "Got it! I can assist with RFPs, features, competitive intelligence, or analytics. What next?";
  };

  const getContextualActions = (input: string) => {
    const lower = input.toLowerCase();
    if (lower.includes("battle")) {
      return [
        { label: "ServiceNow", action: () => console.log("ServiceNow comparison") },
        { label: "Freshservice", action: () => console.log("Freshservice comparison") },
      ];
    }
    return [
      { label: "Upload another RFP", action: () => document.getElementById("file-input")?.click() },
    ];
  };

  return (
    <>
      {/* Launcher Button */}
      <div className="fixed bottom-6 right-6 z-50">
        <Button
          onClick={() => setIsOpen(true)}
          className="w-14 h-14 rounded-full bg-gradient-primary hover:opacity-90 shadow-lg hover:shadow-xl transition-all duration-300 group"
        >
          <MessageCircle className="w-6 h-6 group-hover:scale-110 transition-transform" />
        </Button>
        <div className="absolute -top-2 -left-2 w-4 h-4 bg-primary rounded-full animate-pulse" />
      </div>

      {/* Drawer Assistant */}
      <Drawer open={isOpen} onOpenChange={setIsOpen} direction="right">
        <DrawerContent className="  h-screen flex flex-col border-l border-border bg-background">
          {/* Header */}
          <CardHeader className="p-4 border-b border-border/20 bg-card">
            <div className="flex justify-between items-center">
              <div className="flex items-center gap-2">
                <div className="w-8 h-8 bg-gradient-primary rounded-full flex items-center justify-center">
                  <Sparkles className="w-4 h-4 text-primary-foreground" />
                </div>
                <CardTitle className="text-sm">OneLens AI</CardTitle>
                <Badge className="ml-2 text-xs">ITSM</Badge>
              </div>
              <Button variant="ghost" size="icon" onClick={() => setIsOpen(false)}>
                <X className="w-5 h-5" />
              </Button>
            </div>
          </CardHeader>

          {/* Messages */}
          <CardContent className="flex-1 p-4 overflow-y-auto space-y-4">
            {messages.map((msg) => (
              <div key={msg.id} className={`flex ${msg.type === "user" ? "justify-end" : "justify-start"}`}>
                <div
                  className={`max-w-[80%] rounded-xl px-4 py-2 text-sm whitespace-pre-line ${msg.type === "user"
                    ? "bg-primary text-primary-foreground"
                    : msg.type === "system"
                      ? "bg-muted text-foreground/70 italic"
                      : "bg-muted/50 text-foreground"
                    }`}
                >
                  {msg.content}
                  {msg.actions && (
                    <div className="flex flex-wrap gap-2 mt-3">
                      {msg.actions.map((a, i) => (
                        <Button
                          key={i}
                          variant="outline"
                          size="sm"
                          className="text-xs h-7"
                          onClick={a.action}
                        >
                          {a.label}
                        </Button>
                      ))}
                    </div>
                  )}
                  <div className="text-[10px] opacity-60 mt-1">
                    {msg.timestamp.toLocaleTimeString()}
                  </div>
                </div>
              </div>
            ))}
            {isTyping && (
              <div className="flex justify-start">
                <div className="bg-muted/50 px-3 py-2 rounded-lg flex space-x-1">
                  <div className="w-2 h-2 bg-muted-foreground rounded-full animate-pulse" />
                  <div className="w-2 h-2 bg-muted-foreground rounded-full animate-pulse delay-100" />
                  <div className="w-2 h-2 bg-muted-foreground rounded-full animate-pulse delay-200" />
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </CardContent>

          {/* Input + File Upload */}
          <div className="p-4 border-t border-border/20 bg-card flex items-center gap-2">
            <Input
              placeholder="Ask something or upload a file..."
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleSendMessage()}
              className="flex-1 bg-muted/30"
            />
            <input
              id="file-input"
              type="file"
              className="hidden"
              accept=".pdf,.docx,.txt"
              onChange={handleFileUpload}
            />
            <Button variant="ghost" size="icon" onClick={() => document.getElementById("file-input")?.click()}>
              <UploadCloud className="w-5 h-5" />
            </Button>
            <Button onClick={handleSendMessage} disabled={!inputValue.trim()} className="bg-gradient-primary">
              <Send className="w-4 h-4" />
            </Button>
          </div>
        </DrawerContent>
      </Drawer>
    </>
  );
}
