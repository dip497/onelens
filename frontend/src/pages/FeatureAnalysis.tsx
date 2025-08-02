import { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Markdown } from '@/components/ui/markdown';
import { 
  ArrowLeft, TrendingUp, Building, Globe, BarChart3, 
  MapPin, RefreshCw, Clock, CheckCircle, AlertCircle
} from 'lucide-react';
import { featureApi } from '@/services/api';
import { toast } from 'sonner';

export function FeatureAnalysis() {
  const { featureId } = useParams<{ featureId: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState('trend_analyst');

  // Mock feature data for testing when API fails
  const mockFeature = {
    id: featureId || '',
    title: 'API Integration for User Authentication',
    description: 'OAuth 2.0, SAML, and custom API authentication methods with role-based access control',
    customer_request_count: 27,
    priority_score: { final_score: 85 }
  };

  // Get feature details
  const { data: feature, isLoading: featureLoading, error: featureError } = useQuery({
    queryKey: ['feature', featureId],
    queryFn: () => featureApi.get(featureId!, true),
    enabled: !!featureId,
    retry: 1, // Only retry once
  });

  // Use mock data if API fails
  const displayFeature = feature || (featureError ? mockFeature : null);

  // Agent analysis mutation
  const agentAnalysisMutation = useMutation({
    mutationFn: ({ agentType, forceRefresh }: { agentType: string; forceRefresh?: boolean }) =>
      featureApi.runAgentAnalysis(featureId!, agentType, forceRefresh),
    onSuccess: (data) => {
      queryClient.setQueryData(['agent-analysis', featureId, data.agent_type], data);
      if (!data.cached) {
        toast.success(`${data.agent_type} analysis completed`);
      }
    },
    onError: (error: any) => {
      toast.error(`Analysis failed: ${error.response?.data?.detail || error.message}`);
    },
  });

  // Get cached analysis for current tab - only when explicitly requested
  const { data: analysisData, isLoading: analysisLoading, refetch: refetchAnalysis } = useQuery({
    queryKey: ['agent-analysis', featureId, activeTab],
    queryFn: () => featureApi.runAgentAnalysis(featureId!, activeTab, false),
    enabled: false, // Don't auto-fetch, only fetch when user clicks "Run Analysis"
    staleTime: 1000 * 60 * 60 * 24, // 24 hours
  });

  // Check if we have cached data for the current tab
  const cachedData = queryClient.getQueryData(['agent-analysis', featureId, activeTab]);

  const handleRunAnalysis = (agentType: string, forceRefresh = false) => {
    // If it's the current tab, use refetch
    if (agentType === activeTab) {
      refetchAnalysis();
    } else {
      // For other tabs, call the API directly and cache the result
      featureApi.runAgentAnalysis(featureId!, agentType, forceRefresh)
        .then((data) => {
          queryClient.setQueryData(['agent-analysis', featureId, agentType], data);
          toast.success(`${agentType} analysis completed`);
        })
        .catch((error) => {
          toast.error(`Analysis failed: ${error.response?.data?.detail || error.message}`);
        });
    }
  };

  const agentTabs = [
    {
      id: 'trend_analyst',
      label: 'Market Trends',
      icon: TrendingUp,
      description: 'Current market trends and technology alignment'
    },
    {
      id: 'competitive_analyst',
      label: 'Competitive Analysis',
      icon: Building,
      description: 'Analysis against ManageEngine, Freshservice, HaloITSM'
    },
    {
      id: 'market_opportunity_analyst',
      label: 'Market Forecasting',
      icon: Globe,
      description: 'Market trends and future forecasting with detailed projections'
    },
    {
      id: 'business_impact_analyst',
      label: 'Business Impact',
      icon: BarChart3,
      description: 'Revenue impact and business value assessment'
    },
    {
      id: 'geographic_analyst',
      label: 'Geographic Analysis',
      icon: MapPin,
      description: 'Regional market opportunities and expansion strategies'
    }
  ];

  if (featureLoading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-32 w-full" />
      </div>
    );
  }

  if (!feature) {
    return (
      <div className="text-center py-12">
        <AlertCircle className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
        <h3 className="text-lg font-semibold">Feature not found</h3>
        <p className="text-muted-foreground">The requested feature could not be found.</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center gap-4">
        <Button variant="ghost" size="sm" onClick={() => navigate('/features')}>
          <ArrowLeft className="h-4 w-4 mr-2" />
          Back to Features
        </Button>
      </div>

      {/* Feature Info */}
      <Card>
        <CardHeader>
          <div className="flex items-start justify-between">
            <div>
              <CardTitle className="text-2xl">{feature.title}</CardTitle>
              <CardDescription className="mt-2">
                {feature.description || 'No description available'}
              </CardDescription>
            </div>
            <div className="flex gap-2">
              <Badge variant="secondary">
                {feature.customer_request_count} Customer Requests
              </Badge>
              {feature.priority_score && (
                <Badge variant="outline">
                  Priority: {feature.priority_score.final_score?.toFixed(0)}
                </Badge>
              )}
            </div>
          </div>
        </CardHeader>
      </Card>

      {/* Analysis Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-6">
        <TabsList className="grid w-full grid-cols-5">
          {agentTabs.map((tab) => {
            const Icon = tab.icon;
            return (
              <TabsTrigger key={tab.id} value={tab.id} className="flex items-center gap-2">
                <Icon className="h-4 w-4" />
                <span className="hidden sm:inline">{tab.label}</span>
              </TabsTrigger>
            );
          })}
        </TabsList>

        {agentTabs.map((tab) => (
          <TabsContent key={tab.id} value={tab.id}>
            <Card>
              <CardHeader>
                <div className="flex items-center justify-between">
                  <div>
                    <CardTitle className="flex items-center gap-2">
                      <tab.icon className="h-5 w-5" />
                      {tab.label}
                    </CardTitle>
                    <CardDescription>{tab.description}</CardDescription>
                  </div>
                  <div className="flex items-center gap-2">
                    {(analysisData || cachedData) && (analysisData?.cached || cachedData?.cached) && (
                      <div className="flex items-center gap-1 text-sm text-muted-foreground">
                        <Clock className="h-3 w-3" />
                        Cached {new Date((analysisData?.cached_at || cachedData?.cached_at)).toLocaleString()}
                      </div>
                    )}
                    <Button
                      onClick={() => handleRunAnalysis(tab.id, true)}
                      disabled={analysisLoading && activeTab === tab.id}
                      size="sm"
                    >
                      {(analysisLoading && activeTab === tab.id) ? (
                        <RefreshCw className="h-4 w-4 mr-2 animate-spin" />
                      ) : (
                        <RefreshCw className="h-4 w-4 mr-2" />
                      )}
                      {(analysisData || cachedData) ? 'Refresh Analysis' : 'Run Analysis'}
                    </Button>
                  </div>
                </div>
              </CardHeader>
              <CardContent>
                {(analysisLoading && activeTab === tab.id) ? (
                  <div className="space-y-3">
                    <Skeleton className="h-4 w-full" />
                    <Skeleton className="h-4 w-3/4" />
                    <Skeleton className="h-4 w-1/2" />
                  </div>
                ) : (analysisData?.analysis || cachedData?.analysis) ? (
                  <div className="space-y-4">
                    <div className="flex items-center gap-2 text-sm text-green-600">
                      <CheckCircle className="h-4 w-4" />
                      Analysis completed
                    </div>
                    <Markdown content={analysisData?.analysis || cachedData?.analysis} />
                  </div>
                ) : (
                  <div className="text-center py-8 text-muted-foreground">
                    <BarChart3 className="h-12 w-12 mx-auto mb-4 opacity-50" />
                    <p>No analysis available. Click "Run Analysis" to generate insights.</p>
                  </div>
                )}
              </CardContent>
            </Card>
          </TabsContent>
        ))}
      </Tabs>
    </div>
  );
}
