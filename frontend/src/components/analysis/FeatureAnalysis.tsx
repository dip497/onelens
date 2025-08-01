import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Search, Target, TrendingUp, Download, Filter, AlertTriangle, Zap, CheckCircle, BarChart3, Settings, Shield, Clock, Users } from "lucide-react";
import { Badge } from "@/components/ui/badge";

// Sample ITSM-specific data
const itsmSampleResults = {
  feature: "Incident Management",
  category: "Core ITSM",
  positioning: "Market Leader",
  score: 94,
  maturityLevel: "Advanced",
  complianceScore: 96,
  insights: [
    "Auto-escalation rules 40% faster than industry average",
    "ITIL 4 compliant with comprehensive SLA tracking",
    "Missing AI-powered root cause analysis",
    "Strong integration with monitoring tools",
    "Mobile app needs improvement for field technicians"
  ],
  metrics: {
    mttr: "2.4 hours",
    firstCallResolution: "78%",
    customerSatisfaction: "4.6/5",
    slaCompliance: "94%"
  },
  competitors: [
    { name: "ServiceNow", score: 89, position: "Strong Challenger", strength: "Platform Integration" },
    { name: "Remedy", score: 82, position: "Established Player", strength: "Enterprise Scale" },
    { name: "Freshservice", score: 76, position: "Rising Star", strength: "User Experience" },
    { name: "Jira Service Management", score: 71, position: "Niche Player", strength: "Developer Tools" }
  ],
  riskFactors: [
    { risk: "Vendor Lock-in", level: "Medium", impact: "High" },
    { risk: "Integration Complexity", level: "Low", impact: "Medium" },
    { risk: "Scalability Limits", level: "Low", impact: "Low" }
  ]
};

// Modular Components
const SearchInterface = ({ searchTerm, setSearchTerm, onAnalyze, isAnalyzing, selectedCategory, setSelectedCategory }) => {
  const itsmCategories = [
    "All Categories",
    "Incident Management",
    "Problem Management",
    "Change Management",
    "Asset Management",
    "Knowledge Management",
    "Service Catalog",
    "Workflow Automation",
    "Reporting & Analytics",
    "Mobile Capabilities",
    "Integration Platform"
  ];

  return (
    <Card className="bg-gradient-to-br from-slate-50 to-blue-50 border-slate-200 ">
      <CardHeader>
        <CardTitle className="text-slate-800 flex items-center">
          <Search className="w-5 h-5 mr-2 text-blue-600" />
          ITSM Feature Analysis Engine
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <div>
            <label className="text-sm font-medium text-slate-600 mb-2 block">Feature Name</label>
            <Input
              placeholder="e.g., Incident Management, Change Approval Workflows"
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="h-12 bg-white/50 border-slate-300 focus:border-blue-500"
            />
          </div>
          <div>
            <label className="text-sm font-medium text-slate-600 mb-2 block">ITSM Category</label>
            <select
              value={selectedCategory}
              onChange={(e) => setSelectedCategory(e.target.value)}
              className="h-12 w-full px-3 rounded-md border border-slate-300 bg-white/50 focus:border-blue-500 focus:outline-none"
            >
              {itsmCategories.map(cat => (
                <option key={cat} value={cat}>{cat}</option>
              ))}
            </select>
          </div>
        </div>

        <div className="flex gap-2 flex-wrap">
          <Button variant="outline" size="lg" className="h-12 border-slate-300">
            <Filter className="w-4 h-4 mr-2" />
            Advanced Filters
          </Button>
          <Button variant="outline" size="lg" className="h-12 border-slate-300">
            <Settings className="w-4 h-4 mr-2" />
            Analysis Settings
          </Button>
          <Button
            size="lg"
            className="h-12 bg-gradient-to-r from-blue-600 to-blue-700 hover:from-blue-700 hover:to-blue-800 min-w-[140px]"
            onClick={onAnalyze}
            disabled={!searchTerm || isAnalyzing}
          >
            {isAnalyzing ? "Analyzing..." : "Analyze Feature"}
          </Button>
        </div>

        {isAnalyzing && (
          <div className="mt-6 p-4 rounded-lg bg-blue-50 border border-blue-200">
            <div className="flex items-center space-x-3">
              <div className="animate-spin w-4 h-4 border-2 border-blue-600 border-t-transparent rounded-full" />
              <span className="text-blue-800 font-medium">
                Analyzing "{searchTerm}" across ITSM competitive landscape...
              </span>
            </div>
            <div className="mt-2 text-sm text-blue-600">
              Evaluating ITIL compliance, vendor capabilities, and market positioning.
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
};

const OverviewMetrics = ({ results }) => (
  <Card className="bg-gradient-to-br from-green-50 to-emerald-50 border-green-200 shadow-lg">
    <CardHeader className="flex flex-row items-center justify-between">
      <CardTitle className="text-slate-800">Analysis Overview</CardTitle>
      <div className="flex gap-2">
        <Button variant="outline" size="sm" className="border-slate-300">
          <Download className="w-4 h-4 mr-2" />
          Export Report
        </Button>
        <Button variant="outline" size="sm" className="border-slate-300">
          <BarChart3 className="w-4 h-4 mr-2" />
          Detailed View
        </Button>
      </div>
    </CardHeader>
    <CardContent>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
        <div className="text-center p-4 rounded-lg bg-white/50">
          <div className="text-3xl font-bold text-green-600 mb-2">{results.score}/100</div>
          <div className="text-sm text-slate-600">Overall Score</div>
        </div>
        <div className="text-center p-4 rounded-lg bg-white/50">
          <div className="text-lg font-semibold text-slate-800 mb-2">{results.positioning}</div>
          <div className="text-sm text-slate-600">Market Position</div>
        </div>
        <div className="text-center p-4 rounded-lg bg-white/50">
          <Badge variant="secondary" className="bg-blue-100 text-blue-800 mb-2">
            <Shield className="w-3 h-3 mr-1" />
            {results.maturityLevel}
          </Badge>
          <div className="text-sm text-slate-600">Maturity Level</div>
        </div>
        <div className="text-center p-4 rounded-lg bg-white/50">
          <div className="text-2xl font-bold text-purple-600 mb-2">{results.complianceScore}%</div>
          <div className="text-sm text-slate-600">ITIL Compliance</div>
        </div>
      </div>
    </CardContent>
  </Card>
);

const KeyMetrics = ({ metrics }) => (
  <Card className="bg-gradient-to-br from-purple-50 to-indigo-50 border-purple-200 shadow-lg">
    <CardHeader>
      <CardTitle className="text-slate-800 flex items-center">
        <BarChart3 className="w-5 h-5 mr-2 text-purple-600" />
        Key Performance Metrics
      </CardTitle>
    </CardHeader>
    <CardContent>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="p-4 rounded-lg bg-white/50 border border-purple-100">
          <div className="flex items-center space-x-2 mb-2">
            <Clock className="w-4 h-4 text-purple-600" />
            <span className="text-sm font-medium text-slate-600">MTTR</span>
          </div>
          <div className="text-xl font-bold text-slate-800">{metrics.mttr}</div>
        </div>
        <div className="p-4 rounded-lg bg-white/50 border border-purple-100">
          <div className="flex items-center space-x-2 mb-2">
            <CheckCircle className="w-4 h-4 text-purple-600" />
            <span className="text-sm font-medium text-slate-600">FCR Rate</span>
          </div>
          <div className="text-xl font-bold text-slate-800">{metrics.firstCallResolution}</div>
        </div>
        <div className="p-4 rounded-lg bg-white/50 border border-purple-100">
          <div className="flex items-center space-x-2 mb-2">
            <Users className="w-4 h-4 text-purple-600" />
            <span className="text-sm font-medium text-slate-600">CSAT</span>
          </div>
          <div className="text-xl font-bold text-slate-800">{metrics.customerSatisfaction}</div>
        </div>
        <div className="p-4 rounded-lg bg-white/50 border border-purple-100">
          <div className="flex items-center space-x-2 mb-2">
            <Target className="w-4 h-4 text-purple-600" />
            <span className="text-sm font-medium text-slate-600">SLA Compliance</span>
          </div>
          <div className="text-xl font-bold text-slate-800">{metrics.slaCompliance}</div>
        </div>
      </div>
    </CardContent>
  </Card>
);

const InsightsPanel = ({ insights }) => (
  <Card className="bg-gradient-to-br from-amber-50 to-orange-50 border-amber-200 shadow-lg">
    <CardHeader>
      <CardTitle className="text-slate-800 flex items-center">
        <Zap className="w-5 h-5 mr-2 text-amber-600" />
        Strategic Insights
      </CardTitle>
    </CardHeader>
    <CardContent>
      <div className="space-y-3">
        {insights.map((insight, index) => (
          <div key={index} className="flex items-start space-x-3 p-4 rounded-lg bg-white/60 border border-amber-100">
            <div className="mt-0.5">
              {insight.includes("Missing") || insight.includes("needs improvement") ?
                <AlertTriangle className="w-4 h-4 text-amber-600" /> :
                <CheckCircle className="w-4 h-4 text-green-600" />
              }
            </div>
            <span className="text-slate-700 flex-1">{insight}</span>
          </div>
        ))}
      </div>
    </CardContent>
  </Card>
);

const CompetitiveBenchmark = ({ competitors }) => (
  <Card className="bg-gradient-to-br from-slate-50 to-gray-50 border-slate-200 shadow-lg">
    <CardHeader>
      <CardTitle className="text-slate-800 flex items-center">
        <Target className="w-5 h-5 mr-2 text-slate-600" />
        Competitive Landscape
      </CardTitle>
    </CardHeader>
    <CardContent>
      <div className="space-y-4">
        {competitors.map((competitor, index) => (
          <div key={index} className="flex items-center justify-between p-4 rounded-lg bg-white border border-slate-200 hover:shadow-md transition-shadow">
            <div className="flex items-center space-x-4">
              <div className="w-10 h-10 rounded-full bg-gradient-to-r from-slate-600 to-slate-700 flex items-center justify-center">
                <span className="text-white text-sm font-bold">{index + 1}</span>
              </div>
              <div>
                <div className="font-semibold text-slate-800">{competitor.name}</div>
                <div className="text-sm text-slate-500">{competitor.position}</div>
                <Badge variant="outline" className="text-xs mt-1">
                  {competitor.strength}
                </Badge>
              </div>
            </div>
            <div className="text-right">
              <div className="text-xl font-bold text-slate-800">{competitor.score}/100</div>
              <div className="w-24 h-2 bg-slate-200 rounded-full overflow-hidden mt-1">
                <div
                  className="h-full bg-gradient-to-r from-slate-600 to-slate-700 transition-all duration-500"
                  style={{ width: `${competitor.score}%` }}
                />
              </div>
            </div>
          </div>
        ))}
      </div>
    </CardContent>
  </Card>
);

const RiskAssessment = ({ riskFactors }) => (
  <Card className="bg-gradient-to-br from-red-50 to-pink-50 border-red-200 shadow-lg">
    <CardHeader>
      <CardTitle className="text-slate-800 flex items-center">
        <AlertTriangle className="w-5 h-5 mr-2 text-red-600" />
        Risk Assessment
      </CardTitle>
    </CardHeader>
    <CardContent>
      <div className="space-y-3">
        {riskFactors.map((risk, index) => (
          <div key={index} className="flex items-center justify-between p-4 rounded-lg bg-white/60 border border-red-100">
            <div className="flex items-center space-x-3">
              <AlertTriangle className="w-4 h-4 text-red-500" />
              <span className="font-medium text-slate-800">{risk.risk}</span>
            </div>
            <div className="flex space-x-2">
              <Badge variant={risk.level === 'High' ? 'destructive' : risk.level === 'Medium' ? 'secondary' : 'outline'}>
                {risk.level} Risk
              </Badge>
              <Badge variant="outline">
                {risk.impact} Impact
              </Badge>
            </div>
          </div>
        ))}
      </div>
    </CardContent>
  </Card>
);

export function FeatureAnalysis() {
  const [searchTerm, setSearchTerm] = useState("");
  const [selectedCategory, setSelectedCategory] = useState("All Categories");
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [showResults, setShowResults] = useState(false);

  const handleAnalyze = () => {
    if (!searchTerm) return;

    setIsAnalyzing(true);
    // Simulate analysis with more realistic timing
    setTimeout(() => {
      setIsAnalyzing(false);
      setShowResults(true);
    }, 4000);
  };

  return (
    <div className=" min-h-screen">
      <div className="mb-4">
        <h1 className="text-3xl font-bold text-foreground mb-2">Feature Analysis</h1>
        <p className="text-muted-foreground">Analyse features with competitors</p>
      </div>

      {/* Search Interface */}
      <SearchInterface
        searchTerm={searchTerm}
        setSearchTerm={setSearchTerm}
        onAnalyze={handleAnalyze}
        isAnalyzing={isAnalyzing}
        selectedCategory={selectedCategory}
        setSelectedCategory={setSelectedCategory}
      />

      {/* Results */}
      {showResults && (
        <div className="space-y-6 mt-6 animate-fadeIn">
          {/* Overview Metrics */}
          <OverviewMetrics results={itsmSampleResults} />

          {/* Key Performance Metrics */}
          <KeyMetrics metrics={itsmSampleResults.metrics} />

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Strategic Insights */}
            <InsightsPanel insights={itsmSampleResults.insights} />

            {/* Risk Assessment */}
            <RiskAssessment riskFactors={itsmSampleResults.riskFactors} />
          </div>

          {/* Competitive Benchmark */}
          <CompetitiveBenchmark competitors={itsmSampleResults.competitors} />
        </div>
      )}
    </div>
  );
}