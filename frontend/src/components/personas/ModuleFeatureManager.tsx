import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Plus,
  Edit2,
  Trash2,
  Star,
  StarOff,
  GripVertical,
  TrendingUp,
  Users,
  Zap,
} from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { Skeleton } from '@/components/ui/skeleton';
import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1';

interface ModuleFeature {
  id: string;
  module_id: string;
  name: string;
  description?: string;
  value_proposition?: string;
  is_key_differentiator: boolean;
  competitor_comparison?: string;
  target_segment?: string;
  status: 'Available' | 'Beta' | 'Planned' | 'Discontinued';
  availability_date?: string;
  implementation_complexity: 'Low' | 'Medium' | 'High';
  adoption_rate?: number;
  success_metrics?: string;
  customer_quotes?: string;
  order_index: number;
  epic_feature_id?: string;
}

interface ModuleFeatureManagerProps {
  moduleId: string;
  moduleName: string;
}

export function ModuleFeatureManager({ moduleId, moduleName }: ModuleFeatureManagerProps) {
  const queryClient = useQueryClient();
  const [isCreateDialogOpen, setIsCreateDialogOpen] = useState(false);
  const [editingFeature, setEditingFeature] = useState<ModuleFeature | null>(null);
  const [formData, setFormData] = useState<Partial<ModuleFeature>>({
    name: '',
    description: '',
    value_proposition: '',
    is_key_differentiator: false,
    status: 'Planned',
    implementation_complexity: 'Medium',
  });

  // Fetch module features
  const { data: features, isLoading } = useQuery({
    queryKey: ['module-features', moduleId],
    queryFn: async () => {
      const response = await axios.get<ModuleFeature[]>(
        `${API_BASE_URL}/module-features/?module_id=${moduleId}`
      );
      return response.data;
    },
  });

  // Create feature mutation
  const createMutation = useMutation({
    mutationFn: async (data: Partial<ModuleFeature>) => {
      const response = await axios.post(`${API_BASE_URL}/module-features/`, {
        ...data,
        module_id: moduleId,
      });
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['module-features', moduleId] });
      toast.success('Feature created successfully');
      setIsCreateDialogOpen(false);
      resetForm();
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to create feature');
    },
  });

  // Update feature mutation
  const updateMutation = useMutation({
    mutationFn: async ({ id, data }: { id: string; data: Partial<ModuleFeature> }) => {
      const response = await axios.put(`${API_BASE_URL}/module-features/${id}`, data);
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['module-features', moduleId] });
      toast.success('Feature updated successfully');
      setEditingFeature(null);
      resetForm();
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to update feature');
    },
  });

  // Delete feature mutation
  const deleteMutation = useMutation({
    mutationFn: async (id: string) => {
      await axios.delete(`${API_BASE_URL}/module-features/${id}`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['module-features', moduleId] });
      toast.success('Feature deleted successfully');
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to delete feature');
    },
  });

  // Toggle key differentiator
  const toggleDifferentiator = async (feature: ModuleFeature) => {
    updateMutation.mutate({
      id: feature.id,
      data: { is_key_differentiator: !feature.is_key_differentiator },
    });
  };

  const resetForm = () => {
    setFormData({
      name: '',
      description: '',
      value_proposition: '',
      is_key_differentiator: false,
      status: 'Planned',
      implementation_complexity: 'Medium',
    });
  };

  const handleEdit = (feature: ModuleFeature) => {
    setEditingFeature(feature);
    setFormData({
      name: feature.name,
      description: feature.description,
      value_proposition: feature.value_proposition,
      is_key_differentiator: feature.is_key_differentiator,
      competitor_comparison: feature.competitor_comparison,
      target_segment: feature.target_segment,
      status: feature.status,
      implementation_complexity: feature.implementation_complexity,
      adoption_rate: feature.adoption_rate,
    });
  };

  const handleSubmit = () => {
    if (editingFeature) {
      updateMutation.mutate({ id: editingFeature.id, data: formData });
    } else {
      createMutation.mutate(formData);
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'Available':
        return 'default';
      case 'Beta':
        return 'secondary';
      case 'Planned':
        return 'outline';
      case 'Discontinued':
        return 'destructive';
      default:
        return 'secondary';
    }
  };

  const getComplexityIcon = (complexity: string) => {
    switch (complexity) {
      case 'Low':
        return '🟢';
      case 'Medium':
        return '🟡';
      case 'High':
        return '🔴';
      default:
        return '⚪';
    }
  };

  if (isLoading) {
    return (
      <div className="space-y-4">
        {[...Array(3)].map((_, i) => (
          <Skeleton key={i} className="h-32" />
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-lg font-semibold">Module Features</h3>
          <p className="text-sm text-muted-foreground">
            Sales and marketing features for {moduleName}
          </p>
        </div>
        <Button onClick={() => setIsCreateDialogOpen(true)}>
          <Plus className="mr-2 h-4 w-4" />
          Add Feature
        </Button>
      </div>

      {/* Features List */}
      {features && features.length > 0 ? (
        <div className="space-y-4">
          {features.map((feature) => (
            <Card key={feature.id} className="hover:shadow-md transition-shadow">
              <CardHeader>
                <div className="flex items-start justify-between">
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      <CardTitle className="text-base">
                        {feature.name}
                      </CardTitle>
                      {feature.is_key_differentiator && (
                        <Star className="h-4 w-4 text-yellow-500 fill-yellow-500" />
                      )}
                      <Badge variant={getStatusColor(feature.status) as any}>
                        {feature.status}
                      </Badge>
                      <span className="text-sm">
                        {getComplexityIcon(feature.implementation_complexity)}
                      </span>
                    </div>
                    {feature.description && (
                      <CardDescription>{feature.description}</CardDescription>
                    )}
                  </div>
                  <div className="flex items-center gap-1">
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={() => toggleDifferentiator(feature)}
                    >
                      {feature.is_key_differentiator ? (
                        <Star className="h-4 w-4 text-yellow-500 fill-yellow-500" />
                      ) : (
                        <StarOff className="h-4 w-4" />
                      )}
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={() => handleEdit(feature)}
                    >
                      <Edit2 className="h-4 w-4" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={() => {
                        if (confirm('Delete this feature?')) {
                          deleteMutation.mutate(feature.id);
                        }
                      }}
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                </div>
              </CardHeader>
              <CardContent className="space-y-3">
                {feature.value_proposition && (
                  <div className="flex items-start gap-2">
                    <TrendingUp className="h-4 w-4 text-muted-foreground mt-0.5" />
                    <div>
                      <p className="text-sm font-medium">Value Proposition</p>
                      <p className="text-sm text-muted-foreground">
                        {feature.value_proposition}
                      </p>
                    </div>
                  </div>
                )}
                
                {feature.target_segment && (
                  <div className="flex items-start gap-2">
                    <Users className="h-4 w-4 text-muted-foreground mt-0.5" />
                    <div>
                      <p className="text-sm font-medium">Target Segment</p>
                      <p className="text-sm text-muted-foreground">
                        {feature.target_segment}
                      </p>
                    </div>
                  </div>
                )}
                
                {feature.adoption_rate !== undefined && (
                  <div className="space-y-1">
                    <div className="flex items-center justify-between text-sm">
                      <span>Adoption Rate</span>
                      <span className="font-medium">{feature.adoption_rate}%</span>
                    </div>
                    <Progress value={feature.adoption_rate} className="h-2" />
                  </div>
                )}
                
                {feature.competitor_comparison && (
                  <div className="flex items-start gap-2">
                    <Zap className="h-4 w-4 text-muted-foreground mt-0.5" />
                    <div>
                      <p className="text-sm font-medium">Competitive Edge</p>
                      <p className="text-sm text-muted-foreground">
                        {feature.competitor_comparison}
                      </p>
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>
          ))}
        </div>
      ) : (
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-12">
            <Zap className="h-12 w-12 text-muted-foreground mb-4" />
            <p className="text-muted-foreground mb-4">No features added yet</p>
            <Button onClick={() => setIsCreateDialogOpen(true)}>
              Add Your First Feature
            </Button>
          </CardContent>
        </Card>
      )}

      {/* Create/Edit Dialog */}
      <Dialog
        open={isCreateDialogOpen || !!editingFeature}
        onOpenChange={(open) => {
          if (!open) {
            setIsCreateDialogOpen(false);
            setEditingFeature(null);
            resetForm();
          }
        }}
      >
        <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>
              {editingFeature ? 'Edit Feature' : 'Add Module Feature'}
            </DialogTitle>
            <DialogDescription>
              Create features specifically for sales and marketing purposes
            </DialogDescription>
          </DialogHeader>
          
          <div className="space-y-4">
            <div>
              <label className="text-sm font-medium">Feature Name</label>
              <Input
                value={formData.name}
                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                placeholder="e.g., AI-Powered Analytics"
              />
            </div>
            
            <div>
              <label className="text-sm font-medium">Description</label>
              <Textarea
                value={formData.description}
                onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                placeholder="Brief description of the feature"
                rows={2}
              />
            </div>
            
            <div>
              <label className="text-sm font-medium">Value Proposition</label>
              <Textarea
                value={formData.value_proposition}
                onChange={(e) => setFormData({ ...formData, value_proposition: e.target.value })}
                placeholder="How does this feature provide value to customers?"
                rows={2}
              />
            </div>
            
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="text-sm font-medium">Status</label>
                <Select
                  value={formData.status}
                  onValueChange={(value: any) => setFormData({ ...formData, status: value })}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="Available">Available</SelectItem>
                    <SelectItem value="Beta">Beta</SelectItem>
                    <SelectItem value="Planned">Planned</SelectItem>
                    <SelectItem value="Discontinued">Discontinued</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              
              <div>
                <label className="text-sm font-medium">Implementation Complexity</label>
                <Select
                  value={formData.implementation_complexity}
                  onValueChange={(value: any) =>
                    setFormData({ ...formData, implementation_complexity: value })
                  }
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="Low">Low 🟢</SelectItem>
                    <SelectItem value="Medium">Medium 🟡</SelectItem>
                    <SelectItem value="High">High 🔴</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
            
            <div>
              <label className="text-sm font-medium">Target Segment</label>
              <Input
                value={formData.target_segment}
                onChange={(e) => setFormData({ ...formData, target_segment: e.target.value })}
                placeholder="e.g., Enterprise, SMB, Startup"
              />
            </div>
            
            <div>
              <label className="text-sm font-medium">Competitive Comparison</label>
              <Textarea
                value={formData.competitor_comparison}
                onChange={(e) =>
                  setFormData({ ...formData, competitor_comparison: e.target.value })
                }
                placeholder="How do we compare to competitors on this feature?"
                rows={2}
              />
            </div>
            
            <div>
              <label className="text-sm font-medium">Adoption Rate (%)</label>
              <Input
                type="number"
                min="0"
                max="100"
                value={formData.adoption_rate || ''}
                onChange={(e) =>
                  setFormData({ ...formData, adoption_rate: parseInt(e.target.value) || undefined })
                }
                placeholder="0-100"
              />
            </div>
            
            <div className="flex items-center gap-2">
              <input
                type="checkbox"
                id="key-differentiator"
                checked={formData.is_key_differentiator}
                onChange={(e) =>
                  setFormData({ ...formData, is_key_differentiator: e.target.checked })
                }
                className="rounded"
              />
              <label htmlFor="key-differentiator" className="text-sm font-medium">
                Mark as Key Differentiator ⭐
              </label>
            </div>
          </div>
          
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => {
                setIsCreateDialogOpen(false);
                setEditingFeature(null);
                resetForm();
              }}
            >
              Cancel
            </Button>
            <Button
              onClick={handleSubmit}
              disabled={!formData.name || createMutation.isPending || updateMutation.isPending}
            >
              {createMutation.isPending || updateMutation.isPending
                ? 'Saving...'
                : editingFeature
                ? 'Update'
                : 'Create'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}