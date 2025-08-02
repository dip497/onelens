import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Check, X, Sparkles, Search } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
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
import { Badge } from '@/components/ui/badge';
import { Checkbox } from '@/components/ui/checkbox';
import { Skeleton } from '@/components/ui/skeleton';
import { productsApi } from '@/lib/api/products';
import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1';

interface FeatureAssignmentProps {
  productId: string;
}

interface Feature {
  id: string;
  title: string;
  description?: string;
  module_id?: string;
  is_key_differentiator: boolean;
  epic: {
    id: string;
    title: string;
  };
}

interface Module {
  id: string;
  name: string;
  icon?: string;
  order_index: number;
}

export function FeatureAssignment({ productId }: FeatureAssignmentProps) {
  const queryClient = useQueryClient();
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedModule, setSelectedModule] = useState<string>('all');
  const [selectedFeatures, setSelectedFeatures] = useState<Set<string>>(new Set());

  // Fetch all features
  const { data: features, isLoading: loadingFeatures } = useQuery({
    queryKey: ['features'],
    queryFn: async () => {
      const response = await axios.get<Feature[]>(`${API_BASE_URL}/features`);
      return response.data;
    },
  });

  // Fetch product modules
  const { data: modules, isLoading: loadingModules } = useQuery({
    queryKey: ['product-modules', productId],
    queryFn: () => productsApi.getProductModules(productId),
  });

  // Update feature assignments
  const updateFeatureMutation = useMutation({
    mutationFn: async (updates: Array<{ feature_id: string; module_id: string | null; is_key_differentiator: boolean }>) => {
      // Group updates by module
      const updatesByModule = updates.reduce((acc, update) => {
        const moduleId = update.module_id || 'unassigned';
        if (!acc[moduleId]) {
          acc[moduleId] = [];
        }
        acc[moduleId].push(update);
        return acc;
      }, {} as Record<string, typeof updates>);

      // Update each module's features
      const promises = Object.entries(updatesByModule).map(([moduleId, moduleUpdates]) => {
        if (moduleId !== 'unassigned') {
          return productsApi.updateModuleFeatures(moduleId, moduleUpdates);
        }
        return Promise.resolve();
      });

      return Promise.all(promises);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['features'] });
      queryClient.invalidateQueries({ queryKey: ['product-modules'] });
      toast.success('Feature assignments updated successfully');
      setSelectedFeatures(new Set());
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to update feature assignments');
    },
  });

  const filteredFeatures = features?.filter(feature => {
    const matchesSearch = feature.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
      feature.description?.toLowerCase().includes(searchQuery.toLowerCase());
    
    const matchesModule = selectedModule === 'all' ||
      (selectedModule === 'unassigned' && !feature.module_id) ||
      feature.module_id === selectedModule;
    
    return matchesSearch && matchesModule;
  });

  const handleToggleFeature = (featureId: string) => {
    const newSelected = new Set(selectedFeatures);
    if (newSelected.has(featureId)) {
      newSelected.delete(featureId);
    } else {
      newSelected.add(featureId);
    }
    setSelectedFeatures(newSelected);
  };

  const handleAssignToModule = (moduleId: string | null) => {
    if (selectedFeatures.size === 0) {
      toast.error('Please select features to assign');
      return;
    }

    const updates = Array.from(selectedFeatures).map(featureId => {
      const feature = features?.find(f => f.id === featureId);
      return {
        feature_id: featureId,
        module_id: moduleId,
        is_key_differentiator: feature?.is_key_differentiator || false,
      };
    });

    updateFeatureMutation.mutate(updates);
  };

  const handleToggleDifferentiator = (featureId: string) => {
    const feature = features?.find(f => f.id === featureId);
    if (!feature) return;

    updateFeatureMutation.mutate([{
      feature_id: featureId,
      module_id: feature.module_id || null,
      is_key_differentiator: !feature.is_key_differentiator,
    }]);
  };

  if (loadingFeatures || loadingModules) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-10 w-full" />
        <Skeleton className="h-96 w-full" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold mb-2">Feature Assignment</h2>
        <p className="text-muted-foreground">
          Assign features to product modules and mark key differentiators
        </p>
      </div>

      {/* Filters and Actions */}
      <div className="flex flex-col sm:flex-row gap-4">
        <div className="relative flex-1">
          <Search className="absolute left-2 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Search features..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-8"
          />
        </div>
        <Select value={selectedModule} onValueChange={setSelectedModule}>
          <SelectTrigger className="w-[200px]">
            <SelectValue placeholder="Filter by module" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Features</SelectItem>
            <SelectItem value="unassigned">Unassigned</SelectItem>
            {modules?.map((module) => (
              <SelectItem key={module.id} value={module.id}>
                {module.icon} {module.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {/* Bulk Actions */}
      {selectedFeatures.size > 0 && (
        <Card>
          <CardHeader className="py-3">
            <CardTitle className="text-sm">
              {selectedFeatures.size} features selected
            </CardTitle>
          </CardHeader>
          <CardContent className="flex flex-wrap gap-2">
            <Button
              size="sm"
              variant="outline"
              onClick={() => handleAssignToModule(null)}
            >
              Unassign
            </Button>
            {modules?.map((module) => (
              <Button
                key={module.id}
                size="sm"
                variant="outline"
                onClick={() => handleAssignToModule(module.id)}
              >
                Assign to {module.icon} {module.name}
              </Button>
            ))}
          </CardContent>
        </Card>
      )}

      {/* Features List */}
      <div className="space-y-2">
        {filteredFeatures?.map((feature) => {
          const assignedModule = modules?.find(m => m.id === feature.module_id);
          
          return (
            <Card key={feature.id} className="hover:shadow-sm transition-shadow">
              <CardContent className="py-4">
                <div className="flex items-start gap-4">
                  <Checkbox
                    checked={selectedFeatures.has(feature.id)}
                    onCheckedChange={() => handleToggleFeature(feature.id)}
                  />
                  <div className="flex-1">
                    <div className="flex items-start justify-between">
                      <div>
                        <h4 className="font-medium flex items-center gap-2">
                          {feature.title}
                          {feature.is_key_differentiator && (
                            <Badge variant="default" className="text-xs">
                              <Sparkles className="mr-1 h-3 w-3" />
                              Key Differentiator
                            </Badge>
                          )}
                        </h4>
                        {feature.description && (
                          <p className="text-sm text-muted-foreground mt-1">
                            {feature.description}
                          </p>
                        )}
                        <div className="flex items-center gap-4 mt-2 text-sm">
                          <span className="text-muted-foreground">
                            Epic: {feature.epic.title}
                          </span>
                          {assignedModule ? (
                            <Badge variant="secondary">
                              {assignedModule.icon} {assignedModule.name}
                            </Badge>
                          ) : (
                            <Badge variant="outline">Unassigned</Badge>
                          )}
                        </div>
                      </div>
                      <Button
                        variant={feature.is_key_differentiator ? "default" : "outline"}
                        size="sm"
                        onClick={() => handleToggleDifferentiator(feature.id)}
                      >
                        <Sparkles className="h-4 w-4" />
                      </Button>
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>

      {filteredFeatures?.length === 0 && (
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-12">
            <p className="text-muted-foreground">No features found</p>
          </CardContent>
        </Card>
      )}
    </div>
  );
}