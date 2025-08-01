import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft, Edit, Trash2, PlayCircle, Plus } from 'lucide-react';
import { useEpic, useDeleteEpic, useAnalyzeEpic } from '@/hooks/useEpics';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { format } from 'date-fns';
import { EpicStatus } from '@/types';

export function EpicDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { data: epic, isLoading } = useEpic(id!);
  const deleteEpic = useDeleteEpic();
  const analyzeEpic = useAnalyzeEpic();

  if (isLoading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-12 w-1/3" />
        <Skeleton className="h-32 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (!epic) {
    return (
      <div className="text-center py-12">
        <h2 className="text-2xl font-semibold">Epic not found</h2>
        <Button onClick={() => navigate('/epics')} className="mt-4">
          Back to Epics
        </Button>
      </div>
    );
  }

  const handleDelete = async () => {
    if (confirm('Are you sure you want to delete this epic?')) {
      await deleteEpic.mutateAsync(id!);
      navigate('/epics');
    }
  };

  const handleAnalyze = async () => {
    await analyzeEpic.mutateAsync(id!);
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Button variant="ghost" size="icon" onClick={() => navigate('/epics')}>
            <ArrowLeft className="h-4 w-4" />
          </Button>
          <div>
            <h1 className="text-3xl font-bold">{epic.title}</h1>
            <p className="text-muted-foreground">
              Created {format(new Date(epic.created_at), 'MMMM dd, yyyy')}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {epic.status === EpicStatus.DRAFT && (
            <Button onClick={handleAnalyze} variant="default">
              <PlayCircle className="mr-2 h-4 w-4" />
              Start Analysis
            </Button>
          )}
          <Button variant="outline" onClick={() => navigate(`/epics/${id}/edit`)}>
            <Edit className="mr-2 h-4 w-4" />
            Edit
          </Button>
          <Button variant="outline" onClick={handleDelete}>
            <Trash2 className="mr-2 h-4 w-4" />
            Delete
          </Button>
        </div>
      </div>

      {/* Overview Card */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle>Overview</CardTitle>
            <Badge>{epic.status}</Badge>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <div>
            <h4 className="font-medium mb-1">Description</h4>
            <p className="text-muted-foreground">
              {epic.description || 'No description provided'}
            </p>
          </div>
          <div>
            <h4 className="font-medium mb-1">Business Justification</h4>
            <p className="text-muted-foreground">
              {epic.business_justification || 'No business justification provided'}
            </p>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <h4 className="font-medium mb-1">Last Updated</h4>
              <p className="text-muted-foreground">
                {format(new Date(epic.updated_at), 'MMMM dd, yyyy')}
              </p>
            </div>
            <div>
              <h4 className="font-medium mb-1">Features</h4>
              <p className="text-muted-foreground">
                {epic.features_count || 0} features
              </p>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Tabs */}
      <Tabs defaultValue="features" className="space-y-4">
        <TabsList>
          <TabsTrigger value="features">Features</TabsTrigger>
          <TabsTrigger value="analysis">Analysis</TabsTrigger>
          <TabsTrigger value="timeline">Timeline</TabsTrigger>
        </TabsList>
        
        <TabsContent value="features" className="space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="text-lg font-semibold">Features</h3>
            <Button>
              <Plus className="mr-2 h-4 w-4" />
              Add Feature
            </Button>
          </div>
          <Card>
            <CardContent className="pt-6">
              <div className="text-center py-8 text-muted-foreground">
                No features added yet. Add your first feature to get started.
              </div>
            </CardContent>
          </Card>
        </TabsContent>
        
        <TabsContent value="analysis" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Analysis Results</CardTitle>
              <CardDescription>
                AI-powered analysis of features in this epic
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="text-center py-8 text-muted-foreground">
                {epic.status === EpicStatus.DRAFT
                  ? 'Start analysis to see results'
                  : 'Analysis results will appear here'}
              </div>
            </CardContent>
          </Card>
        </TabsContent>
        
        <TabsContent value="timeline" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Activity Timeline</CardTitle>
              <CardDescription>
                Track all changes and activities for this epic
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="text-center py-8 text-muted-foreground">
                Timeline coming soon...
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}