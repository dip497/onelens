import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { featureApi } from '@/services/api';
import type { Feature, FeatureCreateInput } from '@/types';
import { toast } from 'sonner';

export function useFeatures(epicId?: string) {
  const queryClient = useQueryClient();

  const query = useQuery({
    queryKey: ['features', epicId],
    queryFn: () => featureApi.list({ epic_id: epicId }),
  });

  return {
    features: query.data?.items ?? [],
    total: query.data?.total ?? 0,
    ...query,
  };
}

export function useFeature(id: string, includeAnalysis = false) {
  return useQuery({
    queryKey: ['feature', id, includeAnalysis],
    queryFn: () => featureApi.get(id, includeAnalysis),
    enabled: !!id,
  });
}

export function useCreateFeature() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: FeatureCreateInput) => featureApi.create(data),
    onSuccess: (feature) => {
      queryClient.invalidateQueries({ queryKey: ['features'] });
      queryClient.invalidateQueries({ queryKey: ['features', feature.epic_id] });
      queryClient.invalidateQueries({ queryKey: ['epic', feature.epic_id] });
      toast.success('Feature created successfully');
    },
    onError: (error) => {
      toast.error('Failed to create feature. Please try again.');
    },
  });
}

export function useUpdateFeature() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<FeatureCreateInput> }) =>
      featureApi.update(id, data),
    onSuccess: (feature) => {
      queryClient.invalidateQueries({ queryKey: ['features'] });
      queryClient.invalidateQueries({ queryKey: ['feature', feature.id] });
      queryClient.invalidateQueries({ queryKey: ['features', feature.epic_id] });
      toast.success('Feature updated successfully');
    },
    onError: (error) => {
      toast.error('Failed to update feature. Please try again.');
    },
  });
}

export function useDeleteFeature() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id: string) => featureApi.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['features'] });
      toast.success('Feature deleted successfully');
    },
    onError: (error) => {
      toast.error('Failed to delete feature. Please try again.');
    },
  });
}

export function useAnalyzeFeature() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, analysisTypes }: { id: string; analysisTypes?: string[] }) =>
      featureApi.analyze(id, analysisTypes),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['feature', variables.id] });
      toast.success('Feature analysis has been triggered');
    },
    onError: (error) => {
      toast.error('Failed to start analysis. Please try again.');
    },
  });
}