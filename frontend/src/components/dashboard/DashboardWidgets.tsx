import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { TrendingUp, TrendingDown, Activity, Target, AlertTriangle, CheckCircle } from "lucide-react";
import { Button } from "@/components/ui/button";

const metrics = [
  {
    title: "Active Analyses",
    value: "24",
    change: "+12%",
    trend: "up",
    icon: Activity,
    description: "vs last month"
  },
  {
    title: "Market Alerts",
    value: "8",
    change: "+3",
    trend: "up", 
    icon: AlertTriangle,
    description: "this week"
  },
  {
    title: "Competitor Tracking",
    value: "15",
    change: "0",
    trend: "stable",
    icon: Target,
    description: "companies monitored"
  },
  {
    title: "Success Rate",
    value: "94%",
    change: "+2%",
    trend: "up",
    icon: CheckCircle,
    description: "accuracy score"
  }
];

const recentAnalyses = [
  {
    feature: "AI-Powered Search",
    competitor: "SearchCorp",
    status: "completed",
    score: 85,
    timestamp: "2 hours ago"
  },
  {
    feature: "Mobile SDK",
    competitor: "DevTools Inc",
    status: "in-progress",
    score: null,
    timestamp: "4 hours ago"
  },
  {
    feature: "Cloud Analytics",
    competitor: "DataFlow",
    status: "completed",
    score: 92,
    timestamp: "1 day ago"
  }
];

export function DashboardWidgets() {
  return (
    <div className="space-y-6">
      {/* Metrics Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        {metrics.map((metric) => {
          const Icon = metric.icon;
          const isPositive = metric.trend === "up";
          
          return (
            <Card key={metric.title} className="bg-gradient-card border-border/50 hover:border-primary/30 transition-all duration-300">
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium text-muted-foreground">
                  {metric.title}
                </CardTitle>
                <Icon className="h-4 w-4 text-muted-foreground" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold text-foreground">{metric.value}</div>
                <div className="flex items-center space-x-2 text-xs text-muted-foreground">
                  {metric.trend !== "stable" && (
                    <>
                      {isPositive ? (
                        <TrendingUp className="h-3 w-3 text-success" />
                      ) : (
                        <TrendingDown className="h-3 w-3 text-destructive" />
                      )}
                      <span className={isPositive ? "text-success" : "text-destructive"}>
                        {metric.change}
                      </span>
                    </>
                  )}
                  <span>{metric.description}</span>
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>

      {/* Recent Activity */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card className="bg-gradient-card border-border/50">
          <CardHeader>
            <CardTitle className="text-foreground">Recent Feature Analyses</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {recentAnalyses.map((analysis, index) => (
              <div
                key={index}
                className="flex items-center justify-between p-3 rounded-lg bg-muted/30 border border-border/30"
              >
                <div className="flex-1">
                  <div className="font-medium text-foreground">{analysis.feature}</div>
                  <div className="text-sm text-muted-foreground">vs {analysis.competitor}</div>
                  <div className="text-xs text-muted-foreground">{analysis.timestamp}</div>
                </div>
                <div className="text-right">
                  {analysis.status === "completed" ? (
                    <div className="text-lg font-bold text-foreground">{analysis.score}/100</div>
                  ) : (
                    <div className="text-sm text-warning">Analyzing...</div>
                  )}
                  <div className={`text-xs px-2 py-1 rounded-full ${
                    analysis.status === "completed" 
                      ? "bg-success/20 text-success" 
                      : "bg-warning/20 text-warning"
                  }`}>
                    {analysis.status}
                  </div>
                </div>
              </div>
            ))}
            <Button className="w-full mt-4" variant="outline">
              View All Analyses
            </Button>
          </CardContent>
        </Card>

        {/* Quick Actions */}
        <Card className="bg-gradient-card border-border/50">
          <CardHeader>
            <CardTitle className="text-foreground">Quick Actions</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <Button className="w-full h-12 bg-gradient-primary hover:opacity-90" size="lg">
              Start New Analysis
            </Button>
            <Button className="w-full h-12" variant="outline" size="lg">
              Create Monitoring Profile
            </Button>
            <Button className="w-full h-12" variant="outline" size="lg">
              View Market Alerts
            </Button>
            <div className="mt-6 p-4 rounded-lg bg-accent/20 border border-accent/30">
              <div className="text-sm font-medium text-foreground mb-2">💡 Pro Tip</div>
              <div className="text-xs text-muted-foreground">
                Set up automated monitoring for your top 5 competitors to get instant alerts on new features.
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}