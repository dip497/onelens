import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { 
  TrendingUp, Target, Users, Globe, Trophy, AlertCircle,
  ChevronRight, Building, Briefcase, Shield
} from 'lucide-react';
import { Feature, FeatureAnalysisReport } from '@/types';
import { formatCurrency } from '@/lib/utils';

interface FeatureAnalysisCardProps {
  feature: Feature & {
    analyses?: {
      report?: FeatureAnalysisReport;
    };
  };
}

export function FeatureAnalysisCard({ feature }: FeatureAnalysisCardProps) {
  const report = feature.analyses?.report;
  
  if (!report) {
    return (
      <Card className="border-dashed">
        <CardHeader>
          <CardTitle>{feature.title}</CardTitle>
          <CardDescription>{feature.description}</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex items-center gap-2 text-muted-foreground">
            <AlertCircle className="h-4 w-4" />
            <span className="text-sm">No analysis available</span>
          </div>
        </CardContent>
      </Card>
    );
  }

  const getPriorityColor = (score: number) => {
    if (score >= 70) return 'text-green-600 bg-green-50 border-green-200';
    if (score >= 40) return 'text-yellow-600 bg-yellow-50 border-yellow-200';
    return 'text-gray-600 bg-gray-50 border-gray-200';
  };

  const getImpactBadgeVariant = (level?: string) => {
    switch (level) {
      case 'HIGH': return 'destructive';
      case 'MEDIUM': return 'secondary';
      case 'LOW': return 'outline';
      default: return 'outline';
    }
  };

  return (
    <Card className="overflow-hidden">
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between">
          <div className="space-y-1">
            <CardTitle className="text-xl">{feature.title}</CardTitle>
            <CardDescription>{feature.description}</CardDescription>
          </div>
          <div className={`px-4 py-2 rounded-lg border ${getPriorityColor(report.priority_score || 0)}`}>
            <div className="text-2xl font-bold">{report.priority_score?.toFixed(0) || 'N/A'}</div>
            <div className="text-xs font-medium">Priority Score</div>
          </div>
        </div>
      </CardHeader>
      
      <CardContent>
        <Tabs defaultValue="overview" className="w-full">
          <TabsList className="grid w-full grid-cols-4">
            <TabsTrigger value="overview">Overview</TabsTrigger>
            <TabsTrigger value="market">Market Analysis</TabsTrigger>
            <TabsTrigger value="geographic">Geographic</TabsTrigger>
            <TabsTrigger value="competitive">Competitive</TabsTrigger>
          </TabsList>
          
          <TabsContent value="overview" className="space-y-4 mt-4">
            {/* Trend Alignment */}
            <div className="space-y-2">
              <div className="flex items-center gap-2">
                <TrendingUp className="h-4 w-4 text-blue-600" />
                <span className="font-medium">Trend Alignment</span>
                <Badge variant={report.trend_alignment_status ? "default" : "secondary"}>
                  {report.trend_alignment_status ? "Aligned" : "Not Aligned"}
                </Badge>
              </div>
              
              {report.trend_keywords && report.trend_keywords.length > 0 && (
                <div className="flex flex-wrap gap-1 ml-6">
                  {report.trend_keywords.map((keyword, idx) => (
                    <Badge key={idx} variant="outline" className="text-xs">
                      {keyword}
                    </Badge>
                  ))}
                </div>
              )}
            </div>

            {/* Business Impact */}
            <div className="space-y-2">
              <div className="flex items-center gap-2">
                <Target className="h-4 w-4 text-purple-600" />
                <span className="font-medium">Business Impact</span>
              </div>
              
              <div className="ml-6 grid grid-cols-2 gap-4">
                <div>
                  <div className="text-sm text-muted-foreground">Impact Score</div>
                  <div className="flex items-center gap-2">
                    <Progress value={report.business_impact_score || 0} className="h-2 flex-1" />
                    <span className="text-sm font-medium">{report.business_impact_score || 0}</span>
                  </div>
                </div>
                <div className="space-y-1">
                  <div className="text-sm text-muted-foreground">Revenue Potential</div>
                  <Badge variant={getImpactBadgeVariant(report.revenue_potential)}>
                    {report.revenue_potential || 'Unknown'}
                  </Badge>
                </div>
              </div>
            </div>

            {/* User Adoption */}
            <div className="space-y-2">
              <div className="flex items-center gap-2">
                <Users className="h-4 w-4 text-green-600" />
                <span className="font-medium">User Adoption Forecast</span>
                <Badge variant={getImpactBadgeVariant(report.user_adoption_forecast)}>
                  {report.user_adoption_forecast || 'Unknown'}
                </Badge>
              </div>
            </div>
          </TabsContent>
          
          <TabsContent value="market" className="space-y-4 mt-4">
            {/* Market Opportunity Score */}
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <span className="font-medium">Market Opportunity Score</span>
                <span className="text-2xl font-bold text-blue-600">
                  {report.market_opportunity_score?.toFixed(1) || 'N/A'}
                </span>
              </div>
              <Progress value={(report.market_opportunity_score || 0) * 10} className="h-3" />
            </div>

            {/* Competitor Analysis */}
            <div className="space-y-2">
              <div className="flex items-center gap-2">
                <Trophy className="h-4 w-4" />
                <span className="font-medium">Competitor Analysis</span>
              </div>
              <div className="ml-6 text-sm space-y-1">
                <div>
                  <span className="text-muted-foreground">Analyzed: </span>
                  <span className="font-medium">{report.total_competitors_analyzed || 0} competitors</span>
                </div>
                <div>
                  <span className="text-muted-foreground">Providing feature: </span>
                  <span className="font-medium">{report.competitors_providing_count || 0}</span>
                </div>
              </div>
            </div>

            {/* Market Gaps */}
            {report.competitor_pros_cons?.market_gaps && report.competitor_pros_cons.market_gaps.length > 0 && (
              <div className="space-y-2">
                <span className="font-medium text-sm">Market Gaps Identified</span>
                <div className="space-y-1">
                  {report.competitor_pros_cons.market_gaps.map((gap, idx) => (
                    <div key={idx} className="flex items-start gap-2 text-sm">
                      <ChevronRight className="h-3 w-3 mt-0.5 text-green-600" />
                      <span>{gap}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </TabsContent>
          
          <TabsContent value="geographic" className="space-y-4 mt-4">
            {report.geographic_insights?.top_markets && (
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <span className="font-medium">Top Markets</span>
                  <Badge variant="outline">
                    Total: {formatCurrency(report.geographic_insights.total_market_size)}
                  </Badge>
                </div>
                
                {report.geographic_insights.top_markets.map((market, idx) => (
                  <div key={idx} className="p-3 border rounded-lg space-y-2">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <Globe className="h-4 w-4" />
                        <span className="font-medium">{market.country}</span>
                      </div>
                      <Badge variant={market.opportunity_rating === 'HIGH' ? 'default' : 'secondary'}>
                        {market.opportunity_rating}
                      </Badge>
                    </div>
                    
                    <div className="text-sm text-muted-foreground">
                      Market Size: {formatCurrency(market.market_size)}
                    </div>
                    
                    {market.regulatory_factors.length > 0 && (
                      <div className="flex items-start gap-2 text-xs">
                        <Shield className="h-3 w-3 mt-0.5" />
                        <span>{market.regulatory_factors.join(', ')}</span>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </TabsContent>
          
          <TabsContent value="competitive" className="space-y-4 mt-4">
            {report.competitor_pros_cons?.main_competitors && (
              <div className="space-y-3">
                <span className="font-medium">Main Competitors</span>
                
                {report.competitor_pros_cons.main_competitors.map((competitor, idx) => (
                  <div key={idx} className="p-3 border rounded-lg space-y-2">
                    <div className="flex items-center gap-2">
                      <Building className="h-4 w-4" />
                      <span className="font-medium">{competitor.name}</span>
                    </div>
                    
                    <div className="grid grid-cols-2 gap-2 text-sm">
                      <div className="space-y-1">
                        <span className="text-green-600 font-medium">Strengths</span>
                        {competitor.strengths.map((strength, sIdx) => (
                          <div key={sIdx} className="text-xs text-muted-foreground">• {strength}</div>
                        ))}
                      </div>
                      <div className="space-y-1">
                        <span className="text-red-600 font-medium">Weaknesses</span>
                        {competitor.weaknesses.map((weakness, wIdx) => (
                          <div key={wIdx} className="text-xs text-muted-foreground">• {weakness}</div>
                        ))}
                      </div>
                    </div>
                  </div>
                ))}
                
                {report.competitor_pros_cons.competitive_advantages && 
                 report.competitor_pros_cons.competitive_advantages.length > 0 && (
                  <div className="space-y-2 pt-2">
                    <span className="font-medium text-sm">Our Competitive Advantages</span>
                    <div className="space-y-1">
                      {report.competitor_pros_cons.competitive_advantages.map((advantage, idx) => (
                        <div key={idx} className="flex items-start gap-2 text-sm">
                          <Trophy className="h-3 w-3 mt-0.5 text-yellow-600" />
                          <span>{advantage}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
          </TabsContent>
        </Tabs>

        {/* Metadata */}
        <div className="mt-4 pt-4 border-t text-xs text-muted-foreground">
          <div className="flex items-center justify-between">
            <span>Generated by {report.generated_by_workflow}</span>
            <span>{new Date(report.created_at).toLocaleDateString()}</span>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}