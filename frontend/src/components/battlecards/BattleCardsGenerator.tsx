import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Zap, Download, Share2, Edit, Sparkles, Target, Shield, TrendingUp, Users } from "lucide-react";

const battleCardTemplates = [
  { id: 1, name: "Executive Summary", description: "High-level competitive overview" },
  { id: 2, name: "Feature Comparison", description: "Detailed feature-by-feature analysis" },
  { id: 3, name: "Sales Enablement", description: "Optimized for sales conversations" },
  { id: 4, name: "Technical Deep Dive", description: "In-depth technical comparison" }
];

const competitors = [
  { id: 1, name: "TechCorp", category: "Direct Competitor" },
  { id: 2, name: "InnovateLabs", category: "Emerging Threat" },
  { id: 3, name: "DataFlow Systems", category: "Industry Leader" },
  { id: 4, name: "AgileWorks", category: "Niche Player" }
];

const sampleBattleCard = {
  competitor: "TechCorp",
  overview: "Direct competitor in the enterprise analytics space",
  strengths: [
    "Strong enterprise sales team",
    "Established market presence", 
    "Comprehensive reporting suite"
  ],
  weaknesses: [
    "Legacy architecture limits scalability",
    "Poor mobile experience",
    "Complex pricing structure"
  ],
  differentiators: [
    "Our AI-powered insights vs their manual reporting",
    "Real-time data processing vs batch updates",
    "Intuitive UX vs complex interface"
  ],
  pricing: {
    theirs: "$50K+ annually",
    ours: "$25K annually",
    advantage: "50% cost savings"
  },
  marketShare: "23%",
  customerSentiment: "Mixed reviews on complexity"
};

export function BattleCardsGenerator() {
  const [selectedCompetitor, setSelectedCompetitor] = useState("");
  const [selectedTemplate, setSelectedTemplate] = useState("");
  const [isGenerating, setIsGenerating] = useState(false);
  const [showPreview, setShowPreview] = useState(false);

  const handleGenerate = () => {
    setIsGenerating(true);
    setTimeout(() => {
      setIsGenerating(false);
      setShowPreview(true);
    }, 2500);
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-foreground">Battle Cards Generator</h2>
          <p className="text-muted-foreground">Create competitive intelligence cards with AI-powered insights</p>
        </div>
        <div className="flex items-center space-x-3">
          <Button variant="outline">
            <Share2 className="w-4 h-4 mr-2" />
            Share
          </Button>
          <Button variant="outline">
            <Download className="w-4 h-4 mr-2" />
            Download PDF
          </Button>
        </div>
      </div>

      {/* Configuration */}
      <Card className="bg-gradient-card border-border/50">
        <CardHeader>
          <CardTitle className="text-foreground flex items-center">
            <Zap className="w-5 h-5 mr-2" />
            Battle Card Configuration
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {/* Competitor Selection */}
            <div className="space-y-3">
              <label className="text-sm font-medium text-foreground">Select Competitor</label>
              <Select value={selectedCompetitor} onValueChange={setSelectedCompetitor}>
                <SelectTrigger className="h-12 bg-muted/30">
                  <SelectValue placeholder="Choose competitor to analyze" />
                </SelectTrigger>
                <SelectContent>
                  {competitors.map((competitor) => (
                    <SelectItem key={competitor.id} value={competitor.name}>
                      <div className="flex flex-col">
                        <span>{competitor.name}</span>
                        <span className="text-xs text-muted-foreground">{competitor.category}</span>
                      </div>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {/* Template Selection */}
            <div className="space-y-3">
              <label className="text-sm font-medium text-foreground">Battle Card Template</label>
              <Select value={selectedTemplate} onValueChange={setSelectedTemplate}>
                <SelectTrigger className="h-12 bg-muted/30">
                  <SelectValue placeholder="Choose template style" />
                </SelectTrigger>
                <SelectContent>
                  {battleCardTemplates.map((template) => (
                    <SelectItem key={template.id} value={template.name}>
                      <div className="flex flex-col">
                        <span>{template.name}</span>
                        <span className="text-xs text-muted-foreground">{template.description}</span>
                      </div>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          <div className="flex justify-center">
            <Button 
              size="lg" 
              className="bg-gradient-primary hover:opacity-90 min-w-[200px] h-12"
              onClick={handleGenerate}
              disabled={!selectedCompetitor || !selectedTemplate || isGenerating}
            >
              {isGenerating ? (
                <>
                  <Sparkles className="w-4 h-4 mr-2 animate-pulse-glow" />
                  Generating...
                </>
              ) : (
                <>
                  <Zap className="w-4 h-4 mr-2" />
                  Generate Battle Card
                </>
              )}
            </Button>
          </div>

          {isGenerating && (
            <div className="mt-6 p-4 rounded-lg bg-primary/10 border border-primary/20">
              <div className="flex items-center space-x-3">
                <div className="animate-pulse-glow w-3 h-3 bg-primary rounded-full" />
                <span className="text-primary font-medium">
                  AI analyzing competitive landscape for {selectedCompetitor}...
                </span>
              </div>
              <div className="mt-2 text-sm text-muted-foreground">
                Gathering market intelligence, feature comparisons, and strategic insights.
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Generated Battle Card Preview */}
      {showPreview && (
        <div className="space-y-6 animate-slide-up">
          <Card className="bg-gradient-card border-border/50">
            <CardHeader className="flex flex-row items-center justify-between">
              <CardTitle className="text-foreground">Battle Card: {sampleBattleCard.competitor}</CardTitle>
              <div className="flex space-x-2">
                <Button variant="outline" size="sm">
                  <Edit className="w-4 h-4 mr-2" />
                  Edit
                </Button>
                <Button variant="outline" size="sm">
                  <Download className="w-4 h-4 mr-2" />
                  Export
                </Button>
              </div>
            </CardHeader>
            <CardContent className="space-y-6">
              {/* Quick Stats */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div className="p-4 rounded-lg bg-muted/30 text-center">
                  <Target className="w-6 h-6 text-primary mx-auto mb-2" />
                  <div className="font-medium text-foreground">Market Share</div>
                  <div className="text-xl font-bold text-primary">{sampleBattleCard.marketShare}</div>
                </div>
                <div className="p-4 rounded-lg bg-muted/30 text-center">
                  <TrendingUp className="w-6 h-6 text-success mx-auto mb-2" />
                  <div className="font-medium text-foreground">Cost Advantage</div>
                  <div className="text-xl font-bold text-success">{sampleBattleCard.pricing.advantage}</div>
                </div>
                <div className="p-4 rounded-lg bg-muted/30 text-center">
                  <Users className="w-6 h-6 text-warning mx-auto mb-2" />
                  <div className="font-medium text-foreground">Sentiment</div>
                  <div className="text-sm text-warning">{sampleBattleCard.customerSentiment}</div>
                </div>
              </div>

              {/* Strengths & Weaknesses */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div>
                  <h3 className="font-semibold text-foreground mb-3 flex items-center">
                    <Shield className="w-4 h-4 mr-2 text-success" />
                    Their Strengths
                  </h3>
                  <div className="space-y-2">
                    {sampleBattleCard.strengths.map((strength, index) => (
                      <div key={index} className="p-3 rounded-lg bg-success/10 border border-success/20">
                        <span className="text-foreground text-sm">{strength}</span>
                      </div>
                    ))}
                  </div>
                </div>

                <div>
                  <h3 className="font-semibold text-foreground mb-3 flex items-center">
                    <Target className="w-4 h-4 mr-2 text-destructive" />
                    Their Weaknesses
                  </h3>
                  <div className="space-y-2">
                    {sampleBattleCard.weaknesses.map((weakness, index) => (
                      <div key={index} className="p-3 rounded-lg bg-destructive/10 border border-destructive/20">
                        <span className="text-foreground text-sm">{weakness}</span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>

              {/* Key Differentiators */}
              <div>
                <h3 className="font-semibold text-foreground mb-3 flex items-center">
                  <Sparkles className="w-4 h-4 mr-2 text-primary" />
                  Our Key Differentiators
                </h3>
                <div className="space-y-3">
                  {sampleBattleCard.differentiators.map((diff, index) => (
                    <div key={index} className="p-4 rounded-lg bg-primary/10 border border-primary/20">
                      <span className="text-foreground">{diff}</span>
                    </div>
                  ))}
                </div>
              </div>

              {/* Pricing Comparison */}
              <div className="p-4 rounded-lg bg-gradient-primary/10 border border-primary/20">
                <h3 className="font-semibold text-foreground mb-3">Pricing Advantage</h3>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-center">
                  <div>
                    <div className="text-sm text-muted-foreground">Their Pricing</div>
                    <div className="text-lg font-bold text-foreground">{sampleBattleCard.pricing.theirs}</div>
                  </div>
                  <div>
                    <div className="text-sm text-muted-foreground">Our Pricing</div>
                    <div className="text-lg font-bold text-success">{sampleBattleCard.pricing.ours}</div>
                  </div>
                  <div>
                    <div className="text-sm text-muted-foreground">Savings</div>
                    <div className="text-lg font-bold text-primary">{sampleBattleCard.pricing.advantage}</div>
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}