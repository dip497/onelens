import { useState } from 'react';
import { Plus, Search, Filter, BarChart3, TrendingUp } from 'lucide-react';
import { useEpics, useEpicSummary } from '@/hooks/useEpics';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { EpicStatus } from '@/types';
import { EpicList } from './EpicList';
import { CreateEpicDialog } from './CreateEpicDialog';
import { EpicStatusChart } from './EpicStatusChart';

export function EpicDashboard() {
  const [isCreateDialogOpen, setIsCreateDialogOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<string | undefined>();

  const { data: epics, isLoading, page, setPage, pageSize } = useEpics({
    search: searchQuery,
    status: statusFilter,
  });

  const { data: summary, isLoading: summaryLoading } = useEpicSummary();

  const getStatusColor = (status: EpicStatus) => {
    switch (status) {
      case EpicStatus.DRAFT:
        return 'bg-gray-500';
      case EpicStatus.ANALYSIS_PENDING:
        return 'bg-yellow-500';
      case EpicStatus.ANALYZED:
        return 'bg-blue-500';
      case EpicStatus.APPROVED:
        return 'bg-green-500';
      case EpicStatus.IN_PROGRESS:
        return 'bg-purple-500';
      case EpicStatus.DELIVERED:
        return 'bg-emerald-500';
      default:
        return 'bg-gray-500';
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Epic Analysis Dashboard</h1>
          <p className="text-muted-foreground">
            Manage product epics and track feature analysis progress
          </p>
        </div>
        <Button onClick={() => setIsCreateDialogOpen(true)}>
          <Plus className="mr-2 h-4 w-4" />
          New Epic
        </Button>
      </div>

      {/* Summary Cards */}
      <div className="grid gap-4 md:grid-cols-6">
        {summaryLoading ? (
          Array.from({ length: 6 }).map((_, i) => (
            <Card key={i}>
              <CardHeader className="pb-3">
                <Skeleton className="h-4 w-20" />
              </CardHeader>
              <CardContent>
                <Skeleton className="h-8 w-16" />
              </CardContent>
            </Card>
          ))
        ) : (
          Object.values(EpicStatus).map((status) => {
            const count = summary?.find((s) => s.status === status)?.count || 0;
            return (
              <Card key={status} className="cursor-pointer hover:shadow-md transition-shadow"
                    onClick={() => setStatusFilter(statusFilter === status ? undefined : status)}>
                <CardHeader className="pb-3">
                  <CardTitle className="text-sm font-medium text-muted-foreground">
                    {status}
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="flex items-center gap-2">
                    <div className={`h-3 w-3 rounded-full ${getStatusColor(status)}`} />
                    <span className="text-2xl font-bold">{count}</span>
                  </div>
                </CardContent>
              </Card>
            );
          })
        )}
      </div>

      {/* Charts Row */}
      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <BarChart3 className="h-5 w-5" />
              Epic Status Distribution
            </CardTitle>
            <CardDescription>
              Overview of epics across different stages
            </CardDescription>
          </CardHeader>
          <CardContent>
            <EpicStatusChart data={summary || []} />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <TrendingUp className="h-5 w-5" />
              Analysis Progress
            </CardTitle>
            <CardDescription>
              Feature analysis completion trends
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex items-center justify-center h-[300px] text-muted-foreground">
              Coming soon...
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Filters and Search */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle>Epics</CardTitle>
            <div className="flex items-center gap-2">
              <div className="relative">
                <Search className="absolute left-2 top-2.5 h-4 w-4 text-muted-foreground" />
                <Input
                  placeholder="Search epics..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="pl-8 w-[300px]"
                />
              </div>
              <Select value={statusFilter || "all"} onValueChange={(value) => setStatusFilter(value === "all" ? undefined : value)}>
                <SelectTrigger className="w-[180px]">
                  <SelectValue placeholder="All statuses" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All statuses</SelectItem>
                  {Object.values(EpicStatus).map((status) => (
                    <SelectItem key={status} value={status}>
                      {status}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="space-y-2">
              {Array.from({ length: 5 }).map((_, i) => (
                <Skeleton key={i} className="h-20 w-full" />
              ))}
            </div>
          ) : (
            <EpicList
              epics={epics?.items || []}
              total={epics?.total || 0}
              page={page}
              pageSize={pageSize}
              onPageChange={setPage}
            />
          )}
        </CardContent>
      </Card>

      {/* Create Epic Dialog */}
      <CreateEpicDialog
        open={isCreateDialogOpen}
        onOpenChange={setIsCreateDialogOpen}
      />
    </div>
  );
}