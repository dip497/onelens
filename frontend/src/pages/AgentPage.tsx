import { AgentChat } from '@/components/ag-ui/AgentChat';

export function AgentPage() {
  return (
    <div className="container mx-auto py-8">
      <div className="mb-8 text-center">
        <h1 className="text-3xl font-bold mb-2">OneLens AI Assistant</h1>
        <p className="text-muted-foreground">
          Chat with our AI assistant powered by AG-UI protocol and Agno framework
        </p>
      </div>
      
      <AgentChat
        agentUrl="http://localhost:8000/api/v1/agent"
        title="OneLens Assistant"
      />
    </div>
  );
}
