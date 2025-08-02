import { AgentChat } from "@/components/ag-ui/AgentChat";


export function AgentPage() {
  return (
    <div className="h-screen overflow-hidden flex flex-col">
      <div className="flex-shrink-0 py-4 text-center">
        <h1 className="text-3xl font-bold mb-2">OneLens AI Assistant</h1>
        <p className="text-muted-foreground">
          Chat with our AI assistant powered by AG-UI protocol and Agno framework
        </p>
      </div>

      <div className="flex-1 overflow-hidden">
        <AgentChat
          agentUrl="http://localhost:8000/api/v1/agent"
          title="OneLens Assistant"
        />
      </div>
    </div>
  );
}
