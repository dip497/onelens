import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import {
  Plus,
  FileText,
  Calendar,
  Building2,
  CheckCircle,
  Clock,
  Archive,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { battleCardsApi } from '@/lib/api/battleCards';
import { BattleCardStatus } from '@/types/product';

interface BattleCardListProps {
  productId: string;
}

export function BattleCardList({ productId }: BattleCardListProps) {
  const navigate = useNavigate();
  
  const { data: battleCards, isLoading } = useQuery({
    queryKey: ['battle-cards', productId],
    queryFn: () => battleCardsApi.getBattleCards({ product_id: productId }),
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

  const getStatusBadgeVariant = (status: BattleCardStatus) => {
    switch (status) {
      case BattleCardStatus.PUBLISHED:
        return 'default';
      case BattleCardStatus.DRAFT:
        return 'secondary';
      case BattleCardStatus.ARCHIVED:
        return 'outline';
    }
  };

  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-32 w-full" />
        <Skeleton className="h-32 w-full" />
        <Skeleton className="h-32 w-full" />
      </div>
    );
  }

  const handleCreateBattleCard = () => {
    navigate(`/personas/${productId}/battle-cards/new`);
  };

  const handleViewBattleCard = (battleCardId: string) => {
    navigate(`/personas/${productId}/battle-cards/${battleCardId}`);
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold">Battle Cards</h2>
          <p className="text-muted-foreground">
            Competitive intelligence and sales enablement materials
          </p>
        </div>
        <Button onClick={handleCreateBattleCard}>
          <Plus className="mr-2 h-4 w-4" />
          Create Battle Card
        </Button>
      </div>

      {!battleCards || battleCards.length === 0 ? (
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-12">
            <FileText className="h-12 w-12 text-muted-foreground mb-4" />
            <p className="text-muted-foreground mb-4">No battle cards created yet</p>
            <p className="text-sm text-muted-foreground mb-4">
              Battle cards help your sales team win competitive deals
            </p>
            <Button onClick={handleCreateBattleCard}>
              Create Your First Battle Card
            </Button>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          {battleCards.map((battleCard) => (
            <Card
              key={battleCard.id}
              className="cursor-pointer hover:shadow-lg transition-shadow"
              onClick={() => handleViewBattleCard(battleCard.id)}
            >
              <CardHeader>
                <div className="flex items-start justify-between">
                  <div>
                    <CardTitle className="text-lg flex items-center gap-2">
                      <Building2 className="h-4 w-4" />
                      vs {battleCard.competitor_name}
                    </CardTitle>
                    <CardDescription className="mt-1">
                      Version {battleCard.version}
                    </CardDescription>
                  </div>
                  <Badge variant={getStatusBadgeVariant(battleCard.status)}>
                    <span className="flex items-center gap-1">
                      {getStatusIcon(battleCard.status)}
                      {battleCard.status}
                    </span>
                  </Badge>
                </div>
              </CardHeader>
              <CardContent>
                <div className="space-y-2 text-sm text-muted-foreground">
                  <div className="flex items-center gap-2">
                    <Calendar className="h-3 w-3" />
                    <span>
                      Created {new Date(battleCard.created_at).toLocaleDateString()}
                    </span>
                  </div>
                  {battleCard.published_at && (
                    <div className="flex items-center gap-2">
                      <CheckCircle className="h-3 w-3" />
                      <span>
                        Published {new Date(battleCard.published_at).toLocaleDateString()}
                      </span>
                    </div>
                  )}
                </div>
                <div className="mt-3 flex flex-wrap gap-1">
                  {battleCard.sections.slice(0, 3).map((section) => (
                    <Badge key={section.id} variant="secondary" className="text-xs">
                      {section.section_type}
                    </Badge>
                  ))}
                  {battleCard.sections.length > 3 && (
                    <Badge variant="outline" className="text-xs">
                      +{battleCard.sections.length - 3} more
                    </Badge>
                  )}
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}