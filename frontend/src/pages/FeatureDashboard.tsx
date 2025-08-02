import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { FeatureCard } from '@/components/features/FeatureCard';
import {
  Search, Filter, SortAsc, SortDesc,
  BarChart3, Users, TrendingUp
} from 'lucide-react';
import { featureApi } from '@/services/api';
import { Feature } from '@/types';

export function FeatureDashboard() {
  const [search, setSearch] = useState('');
  const [sortBy, setSortBy] = useState<'priority' | 'requests' | 'title'>('priority');
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('desc');
  const [page, setPage] = useState(1);

  // Fetch features
  const { data: featuresData, isLoading, error } = useQuery({
    queryKey: ['features', { search, page, size: 20 }],
    queryFn: () => featureApi.list({
      search: search || undefined,
      page,
      size: 20,
      // has_priority_score: true  // Temporarily removed to show all features
    }),
  });

  // Sort features
  const sortedFeatures = featuresData?.items?.sort((a, b) => {
    let aValue: any, bValue: any;

    switch (sortBy) {
      case 'priority':
        aValue = a.priority_score?.final_score || 0;
        bValue = b.priority_score?.final_score || 0;
        break;
      case 'requests':
        aValue = a.customer_request_count;
        bValue = b.customer_request_count;
        break;
      case 'title':
        aValue = a.title.toLowerCase();
        bValue = b.title.toLowerCase();
        break;
      default:
        return 0;
    }

    if (sortOrder === 'asc') {
      return aValue > bValue ? 1 : -1;
    } else {
      return aValue < bValue ? 1 : -1;
    }
  }) || [];

  const handleSortToggle = (newSortBy: typeof sortBy) => {
    if (sortBy === newSortBy) {
      setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc');
    } else {
      setSortBy(newSortBy);
      setSortOrder('desc');
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Features</h1>
        <p className="text-muted-foreground">
          Manage and analyze product features across all epics
        </p>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total Features</CardTitle>
            <BarChart3 className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{featuresData?.total || 0}</div>
            <p className="text-xs text-muted-foreground">
              Across all epics
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">High Priority</CardTitle>
            <TrendingUp className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {sortedFeatures.filter(f => (f.priority_score?.final_score || 0) >= 70).length}
            </div>
            <p className="text-xs text-muted-foreground">
              Priority score ≥ 70
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Customer Requests</CardTitle>
            <Users className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {sortedFeatures.reduce((sum, f) => sum + f.customer_request_count, 0)}
            </div>
            <p className="text-xs text-muted-foreground">
              Total requests
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Filters and Search */}
      <Card>
        <CardHeader>
          <CardTitle>Feature Analysis Dashboard</CardTitle>
          <CardDescription>
            View features with priority scoring and detailed analysis
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-col sm:flex-row gap-4">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
              <Input
                placeholder="Search features..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="pl-10"
              />
            </div>

            <div className="flex gap-2">
              <Button
                variant={sortBy === 'priority' ? 'default' : 'outline'}
                size="sm"
                onClick={() => handleSortToggle('priority')}
              >
                Priority
                {sortBy === 'priority' && (
                  sortOrder === 'desc' ? <SortDesc className="ml-2 h-4 w-4" /> : <SortAsc className="ml-2 h-4 w-4" />
                )}
              </Button>

              <Button
                variant={sortBy === 'requests' ? 'default' : 'outline'}
                size="sm"
                onClick={() => handleSortToggle('requests')}
              >
                Requests
                {sortBy === 'requests' && (
                  sortOrder === 'desc' ? <SortDesc className="ml-2 h-4 w-4" /> : <SortAsc className="ml-2 h-4 w-4" />
                )}
              </Button>

              <Button
                variant={sortBy === 'title' ? 'default' : 'outline'}
                size="sm"
                onClick={() => handleSortToggle('title')}
              >
                Name
                {sortBy === 'title' && (
                  sortOrder === 'desc' ? <SortDesc className="ml-2 h-4 w-4" /> : <SortAsc className="ml-2 h-4 w-4" />
                )}
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Features Grid */}
      {isLoading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {Array.from({ length: 6 }).map((_, i) => (
            <Card key={i}>
              <CardHeader>
                <Skeleton className="h-6 w-3/4" />
                <Skeleton className="h-4 w-full" />
              </CardHeader>
              <CardContent>
                <Skeleton className="h-20 w-full" />
              </CardContent>
            </Card>
          ))}
        </div>
      ) : error ? (
        <Card>
          <CardContent className="text-center py-12">
            <p className="text-muted-foreground">Failed to load features</p>
          </CardContent>
        </Card>
      ) : sortedFeatures.length === 0 ? (
        <Card>
          <CardContent className="text-center py-12">
            <BarChart3 className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
            <h3 className="text-lg font-semibold mb-2">No features found</h3>
            <p className="text-muted-foreground">
              {search ? 'Try adjusting your search criteria' : 'Create your first feature to get started'}
            </p>
          </CardContent>
        </Card>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {sortedFeatures.map((feature) => (
            <FeatureCard
              key={feature.id}
              feature={{
                ...feature,
                rfp_occurrence_count: Math.floor(Math.random() * 10), // TODO: Replace with actual RFP count
                tags: ['Not AI Enabled'] // TODO: Replace with actual tags
              }}
            />
          ))}
        </div>
      )}

      {/* Pagination */}
      {featuresData && featuresData.pages > 1 && (
        <div className="flex justify-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => setPage(page - 1)}
            disabled={page === 1}
          >
            Previous
          </Button>

          <div className="flex items-center gap-2">
            {Array.from({ length: Math.min(5, featuresData.pages) }, (_, i) => {
              const pageNum = i + 1;
              return (
                <Button
                  key={pageNum}
                  variant={page === pageNum ? 'default' : 'outline'}
                  size="sm"
                  onClick={() => setPage(pageNum)}
                >
                  {pageNum}
                </Button>
              );
            })}
          </div>

          <Button
            variant="outline"
            size="sm"
            onClick={() => setPage(page + 1)}
            disabled={page === featuresData.pages}
          >
            Next
          </Button>
        </div>
      )}
    </div>
  );
}