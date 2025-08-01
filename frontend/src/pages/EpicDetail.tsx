import { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft, Edit, Trash2, PlayCircle, Plus, MoreVertical } from 'lucide-react';
import { useEpic, useDeleteEpic, useAnalyzeEpic } from '@/hooks/useEpics';
import { useFeatures, useDeleteFeature } from '@/hooks/useFeatures';
import { CreateFeatureDialog } from '@/components/features/CreateFeatureDialog';
import { EditFeatureDialog } from '@/components/features/EditFeatureDialog';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { format } from 'date-fns';
import { EpicStatus, Feature } from '@/types';

export function EpicDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [createFeatureOpen, setCreateFeatureOpen] = useState(false);
  const [editFeatureOpen, setEditFeatureOpen] = useState(false);
  const [featureToEdit, setFeatureToEdit] = useState<Feature | null>(null);
  const [featureToDelete, setFeatureToDelete] = useState<Feature | null>(null);
  const { data: epic, isLoading } = useEpic(id!);
  const { features, isLoading: featuresLoading } = useFeatures(id);
  const deleteEpic = useDeleteEpic();
  const analyzeEpic = useAnalyzeEpic();
  const deleteFeature = useDeleteFeature();

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

  const handleEditFeature = (feature: Feature) => {
    setFeatureToEdit(feature);
    setEditFeatureOpen(true);
  };

  const handleDeleteFeature = async () => {
    if (featureToDelete) {
      await deleteFeature.mutateAsync(featureToDelete.id);
      setFeatureToDelete(null);
    }
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
                {features.length || epic.features_count || 0} features
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
            <Button onClick={() => setCreateFeatureOpen(true)}>
              <Plus className="mr-2 h-4 w-4" />
              Add Feature
            </Button>
          </div>
          {featuresLoading ? (
            <div className="space-y-3">
              <Skeleton className="h-20 w-full" />
              <Skeleton className="h-20 w-full" />
              <Skeleton className="h-20 w-full" />
            </div>
          ) : features.length === 0 ? (
            <Card>
              <CardContent className="pt-6">
                <div className="text-center py-8 text-muted-foreground">
                  No features added yet. Add your first feature to get started.
                </div>
              </CardContent>
            </Card>
          ) : (
            <div className="space-y-3">
              {features.map((feature) => (
                <Card key={feature.id} className="hover:shadow-md transition-shadow">
                  <CardContent className="pt-6">
                    <div className="flex items-start justify-between">
                      <div className="flex-1 space-y-1">
                        <h4 className="font-semibold">{feature.title}</h4>
                        {feature.description && (
                          <p className="text-sm text-muted-foreground">{feature.description}</p>
                        )}
                        <p className="text-xs text-muted-foreground">
                          {feature.customer_request_count} customer requests
                        </p>
                      </div>
                      <div className="flex items-center gap-2">
                        {feature.priority_score && (
                          <Badge variant="secondary">
                            Score: {feature.priority_score.final_score.toFixed(2)}
                          </Badge>
                        )}
                        <DropdownMenu>
                          <DropdownMenuTrigger asChild>
                            <Button variant="ghost" size="icon" className="h-8 w-8">
                              <MoreVertical className="h-4 w-4" />
                            </Button>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent align="end">
                            <DropdownMenuLabel>Actions</DropdownMenuLabel>
                            <DropdownMenuItem onClick={() => handleEditFeature(feature)}>
                              <Edit className="mr-2 h-4 w-4" />
                              Edit
                            </DropdownMenuItem>
                            <DropdownMenuSeparator />
                            <DropdownMenuItem
                              className="text-destructive"
                              onClick={() => setFeatureToDelete(feature)}
                            >
                              <Trash2 className="mr-2 h-4 w-4" />
                              Delete
                            </DropdownMenuItem>
                          </DropdownMenuContent>
                        </DropdownMenu>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
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

      {/* Create Feature Dialog */}
      {epic && (
        <CreateFeatureDialog
          open={createFeatureOpen}
          onOpenChange={setCreateFeatureOpen}
          epicId={epic.id}
        />
      )}

      {/* Edit Feature Dialog */}
      <EditFeatureDialog
        open={editFeatureOpen}
        onOpenChange={setEditFeatureOpen}
        feature={featureToEdit}
      />

      {/* Delete Feature Confirmation */}
      <AlertDialog open={!!featureToDelete} onOpenChange={() => setFeatureToDelete(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Are you sure?</AlertDialogTitle>
            <AlertDialogDescription>
              This will permanently delete the feature "{featureToDelete?.title}".
              This action cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction 
              onClick={handleDeleteFeature} 
              className="bg-destructive text-destructive-foreground"
            >
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}