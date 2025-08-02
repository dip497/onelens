import React, { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation } from '@tanstack/react-query';
import {
  ArrowLeft,
  Building2,
  Sparkles,
  Plus,
  Save,
  FileText,
  Shield,
  Target,
  MessageSquare,
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { battleCardsApi } from '@/lib/api/battleCards';
import { BattleCardSectionType } from '@/types/product';
import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1';

interface Competitor {
  id: string;
  name: string;
  website?: string;
  market_position?: string;
}

const sectionIcons = {
  [BattleCardSectionType.WHY_WE_WIN]: Target,
  [BattleCardSectionType.COMPETITOR_STRENGTHS]: Shield,
  [BattleCardSectionType.OBJECTION_HANDLING]: MessageSquare,
  [BattleCardSectionType.FEATURE_COMPARISON]: FileText,
  [BattleCardSectionType.KEY_DIFFERENTIATORS]: Sparkles,
  [BattleCardSectionType.PRICING_COMPARISON]: FileText,
};

export function BattleCardBuilder() {
  const { productId } = useParams<{ productId: string }>();
  const navigate = useNavigate();
  const [selectedCompetitor, setSelectedCompetitor] = useState<string>('');
  const [sections, setSections] = useState<Map<BattleCardSectionType, any>>(new Map());
  const [isGenerating, setIsGenerating] = useState(false);

  // Fetch competitors
  const { data: competitors, isLoading: loadingCompetitors } = useQuery({
    queryKey: ['competitors'],
    queryFn: async () => {
      const response = await axios.get<Competitor[]>(`${API_BASE_URL}/competitors`);
      return response.data;
    },
  });

  // Generate battle card content
  const generateMutation = useMutation({
    mutationFn: async (competitorId: string) => {
      setIsGenerating(true);
      try {
        const response = await battleCardsApi.generateBattleCard(productId!, {
          competitor_id: competitorId,
          include_sections: [
            BattleCardSectionType.WHY_WE_WIN,
            BattleCardSectionType.COMPETITOR_STRENGTHS,
            BattleCardSectionType.OBJECTION_HANDLING,
            BattleCardSectionType.KEY_DIFFERENTIATORS,
          ],
        });
        return response;
      } finally {
        setIsGenerating(false);
      }
    },
    onSuccess: (battleCard) => {
      // Parse the generated sections
      const newSections = new Map<BattleCardSectionType, any>();
      battleCard.sections.forEach(section => {
        newSections.set(section.section_type, section.content);
      });
      setSections(newSections);
      toast.success('Battle card content generated successfully');
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to generate battle card');
    },
  });

  // Save battle card
  const saveMutation = useMutation({
    mutationFn: async () => {
      if (!selectedCompetitor) {
        throw new Error('Please select a competitor');
      }

      const sectionsArray = Array.from(sections.entries()).map(([type, content], index) => ({
        section_type: type,
        content,
        order_index: index,
      }));

      return battleCardsApi.createBattleCard({
        product_id: productId!,
        competitor_id: selectedCompetitor,
        sections: sectionsArray,
      });
    },
    onSuccess: (battleCard) => {
      toast.success('Battle card saved successfully');
      navigate(`/personas/${productId}/battle-cards/${battleCard.id}`);
    },
    onError: (error: any) => {
      toast.error(error.message || error.response?.data?.detail || 'Failed to save battle card');
    },
  });

  const handleGenerateContent = () => {
    if (!selectedCompetitor) {
      toast.error('Please select a competitor first');
      return;
    }
    generateMutation.mutate(selectedCompetitor);
  };

  const handleSectionUpdate = (type: BattleCardSectionType, content: any) => {
    const newSections = new Map(sections);
    newSections.set(type, content);
    setSections(newSections);
  };

  const renderSectionEditor = (type: BattleCardSectionType, title: string) => {
    const Icon = sectionIcons[type];
    const content = sections.get(type);

    return (
      <Card key={type}>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-lg">
            <Icon className="h-5 w-5" />
            {title}
          </CardTitle>
        </CardHeader>
        <CardContent>
          {type === BattleCardSectionType.WHY_WE_WIN && (
            <div className="space-y-4">
              {content?.points?.map((point: any, index: number) => (
                <div key={index} className="space-y-2">
                  <Input
                    placeholder="Key winning point"
                    value={point.point}
                    onChange={(e) => {
                      const newPoints = [...(content.points || [])];
                      newPoints[index] = { ...point, point: e.target.value };
                      handleSectionUpdate(type, { points: newPoints });
                    }}
                  />
                  <Textarea
                    placeholder="Evidence and talk track"
                    value={point.talk_track}
                    onChange={(e) => {
                      const newPoints = [...(content.points || [])];
                      newPoints[index] = { ...point, talk_track: e.target.value };
                      handleSectionUpdate(type, { points: newPoints });
                    }}
                    className="resize-none"
                  />
                </div>
              )) || (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => handleSectionUpdate(type, {
                    points: [{ point: '', evidence: '', talk_track: '' }]
                  })}
                >
                  <Plus className="mr-2 h-4 w-4" />
                  Add winning point
                </Button>
              )}
            </div>
          )}

          {type === BattleCardSectionType.OBJECTION_HANDLING && (
            <div className="space-y-4">
              {content?.objections?.map((obj: any, index: number) => (
                <div key={index} className="space-y-2">
                  <Input
                    placeholder="Common objection"
                    value={obj.objection}
                    onChange={(e) => {
                      const newObjections = [...(content.objections || [])];
                      newObjections[index] = { ...obj, objection: e.target.value };
                      handleSectionUpdate(type, { objections: newObjections });
                    }}
                  />
                  <Textarea
                    placeholder="Response"
                    value={obj.response}
                    onChange={(e) => {
                      const newObjections = [...(content.objections || [])];
                      newObjections[index] = { ...obj, response: e.target.value };
                      handleSectionUpdate(type, { objections: newObjections });
                    }}
                    className="resize-none"
                  />
                </div>
              )) || (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => handleSectionUpdate(type, {
                    objections: [{ objection: '', response: '', proof_points: [] }]
                  })}
                >
                  <Plus className="mr-2 h-4 w-4" />
                  Add objection
                </Button>
              )}
            </div>
          )}

          {/* Generic content editor for other sections */}
          {!content && ![BattleCardSectionType.WHY_WE_WIN, BattleCardSectionType.OBJECTION_HANDLING].includes(type) && (
            <Textarea
              placeholder={`Enter ${title.toLowerCase()} content...`}
              value=""
              onChange={(e) => handleSectionUpdate(type, { content: e.target.value })}
              className="resize-none"
              rows={4}
            />
          )}
        </CardContent>
      </Card>
    );
  };

  if (loadingCompetitors) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-10 w-64" />
        <Skeleton className="h-96 w-full" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-4">
          <Button
            variant="ghost"
            size="icon"
            onClick={() => navigate(`/personas/${productId}`)}
          >
            <ArrowLeft className="h-4 w-4" />
          </Button>
          <div>
            <h1 className="text-3xl font-bold tracking-tight">Create Battle Card</h1>
            <p className="text-muted-foreground mt-1">
              Generate competitive intelligence for your sales team
            </p>
          </div>
        </div>
        <Button onClick={() => saveMutation.mutate()} disabled={!selectedCompetitor || sections.size === 0}>
          <Save className="mr-2 h-4 w-4" />
          Save Battle Card
        </Button>
      </div>

      {/* Competitor Selection */}
      <Card>
        <CardHeader>
          <CardTitle>Select Competitor</CardTitle>
          <CardDescription>
            Choose the competitor to create a battle card against
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <Select value={selectedCompetitor} onValueChange={setSelectedCompetitor}>
            <SelectTrigger>
              <SelectValue placeholder="Select a competitor" />
            </SelectTrigger>
            <SelectContent>
              {competitors?.map((competitor) => (
                <SelectItem key={competitor.id} value={competitor.id}>
                  <div className="flex items-center gap-2">
                    <Building2 className="h-4 w-4" />
                    {competitor.name}
                    {competitor.market_position && (
                      <Badge variant="outline" className="ml-2">
                        {competitor.market_position}
                      </Badge>
                    )}
                  </div>
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          
          {selectedCompetitor && (
            <Button 
              onClick={handleGenerateContent} 
              disabled={isGenerating || generateMutation.isPending}
              className="w-full"
            >
              <Sparkles className="mr-2 h-4 w-4" />
              {isGenerating ? 'Generating...' : 'Generate Content with AI'}
            </Button>
          )}
        </CardContent>
      </Card>

      {/* Section Editors */}
      {selectedCompetitor && (
        <div className="grid gap-6 md:grid-cols-2">
          {renderSectionEditor(BattleCardSectionType.WHY_WE_WIN, 'Why We Win')}
          {renderSectionEditor(BattleCardSectionType.COMPETITOR_STRENGTHS, 'Competitor Strengths')}
          {renderSectionEditor(BattleCardSectionType.OBJECTION_HANDLING, 'Objection Handling')}
          {renderSectionEditor(BattleCardSectionType.KEY_DIFFERENTIATORS, 'Key Differentiators')}
        </div>
      )}
    </div>
  );
}