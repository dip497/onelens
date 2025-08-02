import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { CheckCircle2, XCircle, MinusCircle, Building2, Globe } from 'lucide-react';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1';

interface CompetitorComparisonProps {
  productId: string;
}

interface Competitor {
  id: string;
  name: string;
  website?: string;
  market_position?: string;
  company_size?: string;
  features?: Array<{
    id: string;
    feature_name: string;
    availability: string;
    strengths?: string;
    weaknesses?: string;
  }>;
}

export function CompetitorComparison({ productId }: CompetitorComparisonProps) {
  const [selectedCompetitors, setSelectedCompetitors] = useState<string[]>([]);

  // Fetch all competitors
  const { data: competitors, isLoading: loadingCompetitors } = useQuery({
    queryKey: ['competitors'],
    queryFn: async () => {
      const response = await axios.get(`${API_BASE_URL}/competitors`);
      return response.data as Competitor[];
    },
  });

  // Fetch product features
  const { data: productModules, isLoading: loadingModules } = useQuery({
    queryKey: ['product-modules', productId],
    queryFn: async () => {
      const response = await axios.get(`${API_BASE_URL}/products/${productId}/modules`);
      return response.data;
    },
  });

  const toggleCompetitor = (competitorId: string) => {
    setSelectedCompetitors(prev =>
      prev.includes(competitorId)
        ? prev.filter(id => id !== competitorId)
        : [...prev, competitorId]
    );
  };

  if (loadingCompetitors || loadingModules) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-32 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  const selectedCompetitorData = competitors?.filter(c => 
    selectedCompetitors.includes(c.id)
  ) || [];

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold mb-2">Competitor Analysis</h2>
        <p className="text-muted-foreground">
          Compare your product features against competitors
        </p>
      </div>

      {/* Competitor Selection */}
      <Card>
        <CardHeader>
          <CardTitle>Select Competitors</CardTitle>
          <CardDescription>
            Choose competitors to include in the comparison
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
            {competitors?.map((competitor) => (
              <div
                key={competitor.id}
                className={`p-4 border rounded-lg cursor-pointer transition-colors ${
                  selectedCompetitors.includes(competitor.id)
                    ? 'border-primary bg-primary/5'
                    : 'border-border hover:border-primary/50'
                }`}
                onClick={() => toggleCompetitor(competitor.id)}
              >
                <div className="flex items-start justify-between">
                  <div>
                    <h4 className="font-medium flex items-center gap-2">
                      <Building2 className="h-4 w-4" />
                      {competitor.name}
                    </h4>
                    {competitor.market_position && (
                      <Badge variant="outline" className="mt-1">
                        {competitor.market_position}
                      </Badge>
                    )}
                  </div>
                  {selectedCompetitors.includes(competitor.id) && (
                    <CheckCircle2 className="h-5 w-5 text-primary" />
                  )}
                </div>
                {competitor.website && (
                  <p className="text-xs text-muted-foreground mt-2 flex items-center gap-1">
                    <Globe className="h-3 w-3" />
                    {competitor.website}
                  </p>
                )}
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Feature Comparison Table */}
      {selectedCompetitorData.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Feature Comparison Matrix</CardTitle>
            <CardDescription>
              How your product stacks up against the competition
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-[200px]">Feature</TableHead>
                    <TableHead>Your Product</TableHead>
                    {selectedCompetitorData.map(competitor => (
                      <TableHead key={competitor.id}>
                        {competitor.name}
                      </TableHead>
                    ))}
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {productModules?.map((module: any) => (
                    <React.Fragment key={module.id}>
                      <TableRow className="bg-muted/50">
                        <TableCell colSpan={2 + selectedCompetitorData.length} className="font-medium">
                          {module.icon} {module.name}
                        </TableCell>
                      </TableRow>
                      {/* TODO: Add actual features when we have feature data */}
                      <TableRow>
                        <TableCell className="pl-8">Sample Feature</TableCell>
                        <TableCell>
                          <CheckCircle2 className="h-5 w-5 text-green-600" />
                        </TableCell>
                        {selectedCompetitorData.map(competitor => (
                          <TableCell key={competitor.id}>
                            <MinusCircle className="h-5 w-5 text-yellow-600" />
                          </TableCell>
                        ))}
                      </TableRow>
                    </React.Fragment>
                  ))}
                </TableBody>
              </Table>
            </div>
            
            <div className="mt-4 flex items-center gap-6 text-sm text-muted-foreground">
              <div className="flex items-center gap-2">
                <CheckCircle2 className="h-4 w-4 text-green-600" />
                <span>Available</span>
              </div>
              <div className="flex items-center gap-2">
                <MinusCircle className="h-4 w-4 text-yellow-600" />
                <span>Partial/Beta</span>
              </div>
              <div className="flex items-center gap-2">
                <XCircle className="h-4 w-4 text-red-600" />
                <span>Not Available</span>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {selectedCompetitorData.length > 0 && (
        <div className="flex justify-end">
          <Button>
            Generate Battle Cards
          </Button>
        </div>
      )}
    </div>
  );
}