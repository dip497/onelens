import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Shield, Plus, Bell, Eye, AlertTriangle, CheckCircle, Clock } from "lucide-react";

const monitoringProfiles = [
  {
    id: 1,
    name: "Competitor Analysis - AI Features",
    companies: ["OpenAI", "Anthropic", "Google AI"],
    keywords: ["GPT", "LLM", "machine learning"],
    frequency: "Daily",
    lastAlert: "2 hours ago",
    alertCount: 5,
    status: "active"
  },
  {
    id: 2,
    name: "Mobile SDK Landscape",
    companies: ["Firebase", "AWS Amplify", "Supabase"],
    keywords: ["mobile SDK", "React Native", "Flutter"],
    frequency: "Weekly",
    lastAlert: "1 day ago", 
    alertCount: 2,
    status: "active"
  },
  {
    id: 3,
    name: "Cloud Infrastructure Watch",
    companies: ["AWS", "Google Cloud", "Azure"],
    keywords: ["cloud", "serverless", "containers"],
    frequency: "Daily",
    lastAlert: "3 days ago",
    alertCount: 0,
    status: "paused"
  }
];

const recentAlerts = [
  {
    id: 1,
    title: "OpenAI announces GPT-5 development",
    source: "TechCrunch",
    timestamp: "2 hours ago",
    priority: "high",
    profile: "Competitor Analysis - AI Features",
    excerpt: "OpenAI CEO hints at significant improvements in reasoning capabilities..."
  },
  {
    id: 2,
    title: "Google releases new Firebase SDK features", 
    source: "Google Blog",
    timestamp: "6 hours ago",
    priority: "medium",
    profile: "Mobile SDK Landscape",
    excerpt: "Enhanced real-time database capabilities and improved offline support..."
  },
  {
    id: 3,
    title: "AWS launches new serverless container service",
    source: "AWS News",
    timestamp: "1 day ago",
    priority: "low",
    profile: "Cloud Infrastructure Watch",
    excerpt: "New service promises 50% faster cold starts for containerized applications..."
  }
];

export function MarketMonitoring() {
  const [showCreateForm, setShowCreateForm] = useState(false);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-foreground">Market Monitoring</h2>
          <p className="text-muted-foreground">Track competitors and market trends in real-time</p>
        </div>
        <Button 
          className="bg-gradient-primary hover:opacity-90"
          onClick={() => setShowCreateForm(!showCreateForm)}
        >
          <Plus className="w-4 h-4 mr-2" />
          Create Profile
        </Button>
      </div>

      {/* Create Form */}
      {showCreateForm && (
        <Card className="bg-gradient-card border-border/50 animate-slide-up">
          <CardHeader>
            <CardTitle className="text-foreground">Create Monitoring Profile</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <Input placeholder="Profile name (e.g., AI Competition Watch)" />
            <Input placeholder="Companies to monitor (comma separated)" />
            <Input placeholder="Keywords to track (comma separated)" />
            <div className="flex gap-2">
              <Button className="bg-gradient-primary hover:opacity-90">Create Profile</Button>
              <Button variant="outline" onClick={() => setShowCreateForm(false)}>Cancel</Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Monitoring Profiles */}
      <Card className="bg-gradient-card border-border/50">
        <CardHeader>
          <CardTitle className="text-foreground flex items-center">
            <Shield className="w-5 h-5 mr-2" />
            Active Monitoring Profiles
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {monitoringProfiles.map((profile) => (
            <div key={profile.id} className="p-4 rounded-lg bg-muted/30 border border-border/30">
              <div className="flex items-start justify-between mb-3">
                <div className="flex-1">
                  <div className="flex items-center space-x-2 mb-2">
                    <h3 className="font-semibold text-foreground">{profile.name}</h3>
                    <Badge variant={profile.status === "active" ? "default" : "secondary"}>
                      {profile.status}
                    </Badge>
                  </div>
                  <div className="text-sm text-muted-foreground mb-2">
                    <strong>Companies:</strong> {profile.companies.join(", ")}
                  </div>
                  <div className="text-sm text-muted-foreground">
                    <strong>Keywords:</strong> {profile.keywords.join(", ")}
                  </div>
                </div>
                <div className="text-right">
                  <div className="flex items-center space-x-2 mb-2">
                    <Bell className="w-4 h-4 text-primary" />
                    <span className="text-sm font-medium text-foreground">{profile.alertCount} alerts</span>
                  </div>
                  <div className="text-xs text-muted-foreground">Last: {profile.lastAlert}</div>
                </div>
              </div>
              <div className="flex items-center justify-between">
                <div className="flex items-center space-x-3 text-sm text-muted-foreground">
                  <Clock className="w-4 h-4" />
                  <span>{profile.frequency} monitoring</span>
                </div>
                <div className="flex space-x-2">
                  <Button variant="outline" size="sm">
                    <Eye className="w-4 h-4 mr-1" />
                    View
                  </Button>
                  <Button variant="outline" size="sm">
                    Edit
                  </Button>
                </div>
              </div>
            </div>
          ))}
        </CardContent>
      </Card>

      {/* Recent Alerts */}
      <Card className="bg-gradient-card border-border/50">
        <CardHeader>
          <CardTitle className="text-foreground flex items-center justify-between">
            <span className="flex items-center">
              <AlertTriangle className="w-5 h-5 mr-2" />
              Recent Alerts
            </span>
            <Badge variant="secondary" className="bg-primary/20 text-primary">
              {recentAlerts.length} new
            </Badge>
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {recentAlerts.map((alert) => (
            <div key={alert.id} className="p-4 rounded-lg bg-muted/30 border border-border/30 hover:border-primary/30 transition-colors">
              <div className="flex items-start justify-between mb-2">
                <div className="flex-1">
                  <div className="flex items-center space-x-2 mb-1">
                    <h4 className="font-medium text-foreground">{alert.title}</h4>
                    <Badge 
                      variant={alert.priority === "high" ? "destructive" : 
                               alert.priority === "medium" ? "default" : "secondary"}
                      className="text-xs"
                    >
                      {alert.priority}
                    </Badge>
                  </div>
                  <p className="text-sm text-muted-foreground mb-2">{alert.excerpt}</p>
                  <div className="flex items-center space-x-4 text-xs text-muted-foreground">
                    <span>{alert.source}</span>
                    <span>•</span>
                    <span>{alert.timestamp}</span>
                    <span>•</span>
                    <span>{alert.profile}</span>
                  </div>
                </div>
                <Button variant="outline" size="sm">
                  <Eye className="w-4 h-4" />
                </Button>
              </div>
            </div>
          ))}
          <Button variant="outline" className="w-full">
            View All Alerts
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}