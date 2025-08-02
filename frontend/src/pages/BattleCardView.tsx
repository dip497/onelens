import React from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation } from '@tanstack/react-query';
import {
  ArrowLeft,
  Edit2,
  Trash2,
  Download,
  Share2,
  CheckCircle,
  Target,
  Shield,
  MessageSquare,
  Sparkles,
  Archive,
  Clock,
} from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Separator } from '@/components/ui/separator';
import { Skeleton } from '@/components/ui/skeleton';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { battleCardsApi } from '@/lib/api/battleCards';
import { BattleCardStatus, BattleCardSectionType } from '@/types/product';
import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1';

const sectionIcons = {
  [BattleCardSectionType.WHY_WE_WIN]: Target,
  [BattleCardSectionType.COMPETITOR_STRENGTHS]: Shield,
  [BattleCardSectionType.OBJECTION_HANDLING]: MessageSquare,
  [BattleCardSectionType.KEY_DIFFERENTIATORS]: Sparkles,
  [BattleCardSectionType.FEATURE_COMPARISON]: Shield,
  [BattleCardSectionType.PRICING_COMPARISON]: Shield,
};

const sectionTitles = {
  [BattleCardSectionType.WHY_WE_WIN]: 'Why We Win',
  [BattleCardSectionType.COMPETITOR_STRENGTHS]: 'Competitor Strengths',
  [BattleCardSectionType.OBJECTION_HANDLING]: 'Objection Handling',
  [BattleCardSectionType.KEY_DIFFERENTIATORS]: 'Key Differentiators',
  [BattleCardSectionType.FEATURE_COMPARISON]: 'Feature Comparison',
  [BattleCardSectionType.PRICING_COMPARISON]: 'Pricing Comparison',
};

export function BattleCardView() {
  const { productId, battleCardId } = useParams<{
    productId: string;
    battleCardId: string;
  }>();
  const navigate = useNavigate();

  const { data: battleCard, isLoading, refetch } = useQuery({
    queryKey: ['battle-card', battleCardId],
    queryFn: async () => {
      const response = await axios.get(
        `${API_BASE_URL}/battle-cards/${battleCardId}`
      );
      return response.data;
    },
    enabled: !!battleCardId,
  });

  const publishMutation = useMutation({
    mutationFn: async () => {
      const response = await axios.post(
        `${API_BASE_URL}/battle-cards/${battleCardId}/publish`
      );
      return response.data;
    },
    onSuccess: () => {
      toast.success('Battle card published successfully');
      refetch();
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to publish battle card');
    },
  });

  const archiveMutation = useMutation({
    mutationFn: async () => {
      const response = await axios.post(
        `${API_BASE_URL}/battle-cards/${battleCardId}/archive`
      );
      return response.data;
    },
    onSuccess: () => {
      toast.success('Battle card archived successfully');
      refetch();
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to archive battle card');
    },
  });

  const deleteMutation = useMutation({
    mutationFn: async () => {
      await axios.delete(`${API_BASE_URL}/battle-cards/${battleCardId}`);
    },
    onSuccess: () => {
      toast.success('Battle card deleted successfully');
      navigate(`/personas/${productId}/battle-cards`);
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to delete battle card');
    },
  });

  const getStatusIcon = (status: BattleCardStatus) => {
    switch (status) {
      case BattleCardStatus.PUBLISHED:
        return <CheckCircle className="h-4 w-4 text-green-600" />;
      case BattleCardStatus.DRAFT:
        return <Clock className="h-4 w-4 text-yellow-600" />;
      case BattleCardStatus.ARCHIVED:
        return <Archive className="h-4 w-4 text-gray-600" />;
    }
  };

  const renderSectionContent = (section: any) => {
    const content = section.content;
    
    if (section.section_type === BattleCardSectionType.WHY_WE_WIN && content.points) {
      return (
        <div className="space-y-4">
          {content.points.map((point: any, index: number) => (
            <div key={index} className="border-l-4 border-primary pl-4">
              <h4 className="font-semibold">{point.point}</h4>
              {point.evidence && (
                <p className="text-sm text-muted-foreground mt-1">
                  Evidence: {point.evidence}
                </p>
              )}
              {point.talk_track && (
                <p className="text-sm mt-2 italic">
                  Talk Track: {point.talk_track}
                </p>
              )}
            </div>
          ))}
        </div>
      );
    }
    
    if (section.section_type === BattleCardSectionType.OBJECTION_HANDLING && content.objections) {
      return (
        <div className="space-y-4">
          {content.objections.map((obj: any, index: number) => (
            <div key={index} className="space-y-2">
              <div className="flex items-start gap-2">
                <MessageSquare className="h-4 w-4 text-muted-foreground mt-1" />
                <div className="flex-1">
                  <p className="font-medium text-destructive">
                    "{obj.objection}"
                  </p>
                  <p className="text-sm mt-2">{obj.response}</p>
                  {obj.proof_points && obj.proof_points.length > 0 && (
                    <ul className="list-disc list-inside text-sm text-muted-foreground mt-2">
                      {obj.proof_points.map((point: string, i: number) => (
                        <li key={i}>{point}</li>
                      ))}
                    </ul>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      );
    }
    
    if (section.section_type === BattleCardSectionType.KEY_DIFFERENTIATORS && content.differentiators) {
      return (
        <div className="grid gap-3 md:grid-cols-2">
          {content.differentiators.map((diff: any, index: number) => (
            <Card key={index} className="bg-secondary/10">
              <CardHeader className="pb-3">
                <CardTitle className="text-sm flex items-center gap-2">
                  <Sparkles className="h-4 w-4 text-yellow-600" />
                  {diff.feature}
                </CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-sm text-muted-foreground">
                  {diff.description}
                </p>
                {diff.value_prop && (
                  <p className="text-sm font-medium mt-2">
                    Value: {diff.value_prop}
                  </p>
                )}
              </CardContent>
            </Card>
          ))}
        </div>
      );
    }
    
    // Default rendering for other sections or plain text
    if (typeof content === 'string') {
      return <p className="text-sm whitespace-pre-wrap">{content}</p>;
    }
    
    return (
      <pre className="text-sm whitespace-pre-wrap bg-secondary/20 p-4 rounded">
        {JSON.stringify(content, null, 2)}
      </pre>
    );
  };

  if (isLoading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-10 w-64" />
        <Skeleton className="h-96 w-full" />
      </div>
    );
  }

  if (!battleCard) {
    return (
      <div className="flex items-center justify-center h-96">
        <Card className="w-96">
          <CardHeader>
            <CardTitle>Battle Card Not Found</CardTitle>
            <CardDescription>
              The battle card you're looking for doesn't exist.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Button onClick={() => navigate(`/personas/${productId}`)}>
              Back to Product
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div className="flex items-start gap-4">
          <Button
            variant="ghost"
            size="icon"
            onClick={() => navigate(`/personas/${productId}`)}
          >
            <ArrowLeft className="h-4 w-4" />
          </Button>
          <div>
            <h1 className="text-3xl font-bold">
              Battle Card vs {battleCard.competitor_name}
            </h1>
            <div className="flex items-center gap-4 mt-2">
              <Badge variant="secondary">
                {getStatusIcon(battleCard.status)}
                <span className="ml-1">{battleCard.status}</span>
              </Badge>
              <span className="text-sm text-muted-foreground">
                Version {battleCard.version}
              </span>
              {battleCard.published_at && (
                <span className="text-sm text-muted-foreground">
                  Published {new Date(battleCard.published_at).toLocaleDateString()}
                </span>
              )}
            </div>
          </div>
        </div>
        
        <div className="flex items-center gap-2">
          {battleCard.status === BattleCardStatus.DRAFT && (
            <Button onClick={() => publishMutation.mutate()}>
              <CheckCircle className="mr-2 h-4 w-4" />
              Publish
            </Button>
          )}
          
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="outline">
                Actions
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem
                onClick={() => navigate(`/personas/${productId}/battle-cards/${battleCardId}/edit`)}
              >
                <Edit2 className="mr-2 h-4 w-4" />
                Edit
              </DropdownMenuItem>
              <DropdownMenuItem>
                <Download className="mr-2 h-4 w-4" />
                Export PDF
              </DropdownMenuItem>
              <DropdownMenuItem>
                <Share2 className="mr-2 h-4 w-4" />
                Share
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              {battleCard.status !== BattleCardStatus.ARCHIVED && (
                <DropdownMenuItem onClick={() => archiveMutation.mutate()}>
                  <Archive className="mr-2 h-4 w-4" />
                  Archive
                </DropdownMenuItem>
              )}
              <DropdownMenuItem
                className="text-destructive"
                onClick={() => {
                  if (confirm('Are you sure you want to delete this battle card?')) {
                    deleteMutation.mutate();
                  }
                }}
              >
                <Trash2 className="mr-2 h-4 w-4" />
                Delete
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>

      {/* Sections */}
      <div className="space-y-6">
        {battleCard.sections
          .sort((a: any, b: any) => a.order_index - b.order_index)
          .map((section: any) => {
            const Icon = sectionIcons[section.section_type] || Shield;
            const title = sectionTitles[section.section_type] || section.section_type;
            
            return (
              <Card key={section.id}>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <Icon className="h-5 w-5" />
                    {title}
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  {renderSectionContent(section)}
                </CardContent>
              </Card>
            );
          })}
      </div>
    </div>
  );
}