import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { epicApi } from '@/services/api';
import type { Epic, EpicCreateInput, PaginatedResponse } from '@/types';
import { toast } from 'sonner';

// Query keys
const EPIC_QUERY_KEY = 'epics';

export function useEpics(params?: {
  page?: number;
  size?: number;
  status?: string;
  search?: string;
}) {
  const [page, setPage] = useState(params?.page || 1);
  const [pageSize, setPageSize] = useState(params?.size || 10);

  const query = useQuery({
    queryKey: [EPIC_QUERY_KEY, 'list', { ...params, page, size: pageSize }],
    queryFn: () => epicApi.list({ ...params, page, size: pageSize }),
  });

  return {
    ...query,
    page,
    pageSize,
    setPage,
    setPageSize,
  };
}

export function useEpic(id: string) {
  return useQuery({
    queryKey: [EPIC_QUERY_KEY, id],
    queryFn: () => epicApi.get(id),
    enabled: !!id,
  });
}

export function useCreateEpic() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: EpicCreateInput) => epicApi.create(data),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: [EPIC_QUERY_KEY, 'list'] });
      queryClient.setQueryData([EPIC_QUERY_KEY, data.id], data);
      toast.success('Epic created successfully');
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to create epic');
    },
  });
}

export function useUpdateEpic() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<EpicCreateInput> }) =>
      epicApi.update(id, data),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: [EPIC_QUERY_KEY, 'list'] });
      queryClient.setQueryData([EPIC_QUERY_KEY, data.id], data);
      toast.success('Epic updated successfully');
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to update epic');
    },
  });
}

export function useDeleteEpic() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id: string) => epicApi.delete(id),
    onSuccess: (_, id) => {
      queryClient.invalidateQueries({ queryKey: [EPIC_QUERY_KEY, 'list'] });
      queryClient.removeQueries({ queryKey: [EPIC_QUERY_KEY, id] });
      toast.success('Epic deleted successfully');
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to delete epic');
    },
  });
}

export function useAnalyzeEpic() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id: string) => epicApi.analyze(id),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: [EPIC_QUERY_KEY, data.epic_id] });
      queryClient.invalidateQueries({ queryKey: [EPIC_QUERY_KEY, 'list'] });
      toast.success('Analysis started successfully');
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to start analysis');
    },
  });
}

export function useEpicSummary() {
  return useQuery({
    queryKey: [EPIC_QUERY_KEY, 'summary'],
    queryFn: () => epicApi.getSummaryByStatus(),
  });
}