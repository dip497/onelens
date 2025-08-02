import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Plus,
  Building2,
  Globe,
  Edit2,
  Trash2,
  Sparkles,
  Search,
  BarChart3,
} from 'lucide-react';
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
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1';

const competitorFormSchema = z.object({
  name: z.string().min(1, 'Name is required').max(255),
  website: z.string().url().optional().or(z.literal('')),
  market_position: z.enum(['Leader', 'Challenger', 'Visionary', 'Niche']).optional(),
  company_size: z.enum(['Startup', 'SMB', 'Enterprise', 'Large Enterprise']).optional(),
  funding_stage: z.string().optional(),
});

type CompetitorFormValues = z.infer<typeof competitorFormSchema>;

interface Competitor {
  id: string;
  name: string;
  website?: string;
  market_position?: string;
  company_size?: string;
  funding_stage?: string;
  features?: Array<{
    id: string;
    feature_name: string;
    availability?: string;
  }>;
  created_at: string;
  updated_at: string;
}

export function CompetitorManagement() {
  const queryClient = useQueryClient();
  const [searchQuery, setSearchQuery] = useState('');
  const [isCreateDialogOpen, setIsCreateDialogOpen] = useState(false);
  const [editingCompetitor, setEditingCompetitor] = useState<Competitor | null>(null);
  const [analyzingCompetitor, setAnalyzingCompetitor] = useState<string | null>(null);

  const { data: competitors, isLoading } = useQuery({
    queryKey: ['competitors'],
    queryFn: async () => {
      const response = await axios.get<Competitor[]>(`${API_BASE_URL}/competitors`);
      return response.data;
    },
  });

  const form = useForm<CompetitorFormValues>({
    resolver: zodResolver(competitorFormSchema),
    defaultValues: {
      name: '',
      website: '',
      market_position: undefined,
      company_size: undefined,
      funding_stage: '',
    },
  });

  const createMutation = useMutation({
    mutationFn: async (data: CompetitorFormValues) => {
      const response = await axios.post(`${API_BASE_URL}/competitors`, data);
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['competitors'] });
      toast.success('Competitor added successfully');
      setIsCreateDialogOpen(false);
      form.reset();
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to add competitor');
    },
  });

  const updateMutation = useMutation({
    mutationFn: async ({ id, data }: { id: string; data: CompetitorFormValues }) => {
      const response = await axios.put(`${API_BASE_URL}/competitors/${id}`, data);
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['competitors'] });
      toast.success('Competitor updated successfully');
      setEditingCompetitor(null);
      form.reset();
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to update competitor');
    },
  });

  const deleteMutation = useMutation({
    mutationFn: async (id: string) => {
      await axios.delete(`${API_BASE_URL}/competitors/${id}`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['competitors'] });
      toast.success('Competitor deleted successfully');
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to delete competitor');
    },
  });

  const analyzeMutation = useMutation({
    mutationFn: async (competitorId: string) => {
      const response = await axios.post(`${API_BASE_URL}/competitors/${competitorId}/analyze`);
      return response.data;
    },
    onSuccess: (data) => {
      toast.success('Analysis started. This may take a few moments.');
      setAnalyzingCompetitor(null);
      // Refresh competitors after a delay to show updated features
      setTimeout(() => {
        queryClient.invalidateQueries({ queryKey: ['competitors'] });
      }, 3000);
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to analyze competitor');
      setAnalyzingCompetitor(null);
    },
  });

  const handleEdit = (competitor: Competitor) => {
    setEditingCompetitor(competitor);
    form.reset({
      name: competitor.name,
      website: competitor.website || '',
      market_position: competitor.market_position as any,
      company_size: competitor.company_size as any,
      funding_stage: competitor.funding_stage || '',
    });
  };

  const handleDelete = (id: string) => {
    if (confirm('Are you sure you want to delete this competitor?')) {
      deleteMutation.mutate(id);
    }
  };

  const handleAnalyze = (competitorId: string) => {
    setAnalyzingCompetitor(competitorId);
    analyzeMutation.mutate(competitorId);
  };

  const onSubmit = (values: CompetitorFormValues) => {
    if (editingCompetitor) {
      updateMutation.mutate({ id: editingCompetitor.id, data: values });
    } else {
      createMutation.mutate(values);
    }
  };

  const filteredCompetitors = competitors?.filter(competitor =>
    competitor.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
    competitor.website?.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const getMarketPositionColor = (position?: string) => {
    switch (position) {
      case 'Leader': return 'default';
      case 'Challenger': return 'secondary';
      case 'Visionary': return 'outline';
      default: return 'secondary';
    }
  };

  if (isLoading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-10 w-64" />
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {[...Array(6)].map((_, i) => (
            <Skeleton key={i} className="h-48" />
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Competitor Management</h1>
        <p className="text-muted-foreground">
          Track and analyze your competitors to stay ahead
        </p>
      </div>

      {/* Stats */}
      <div className="grid gap-4 md:grid-cols-3">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total Competitors</CardTitle>
            <Building2 className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{competitors?.length || 0}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Features Tracked</CardTitle>
            <BarChart3 className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {competitors?.reduce((acc, c) => acc + (c.features?.length || 0), 0) || 0}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Market Leaders</CardTitle>
            <Sparkles className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {competitors?.filter(c => c.market_position === 'Leader').length || 0}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Actions Bar */}
      <div className="flex items-center gap-4">
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-2 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Search competitors..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-8"
          />
        </div>
        <Button onClick={() => setIsCreateDialogOpen(true)}>
          <Plus className="mr-2 h-4 w-4" />
          Add Competitor
        </Button>
      </div>

      {/* Competitors Grid */}
      {filteredCompetitors && filteredCompetitors.length > 0 ? (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {filteredCompetitors.map((competitor) => (
            <Card key={competitor.id} className="hover:shadow-lg transition-shadow">
              <CardHeader>
                <div className="flex items-start justify-between">
                  <div>
                    <CardTitle className="text-lg flex items-center gap-2">
                      <Building2 className="h-5 w-5" />
                      {competitor.name}
                    </CardTitle>
                    {competitor.market_position && (
                      <Badge 
                        variant={getMarketPositionColor(competitor.market_position) as any}
                        className="mt-2"
                      >
                        {competitor.market_position}
                      </Badge>
                    )}
                  </div>
                  <div className="flex items-center gap-1">
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={() => handleEdit(competitor)}
                    >
                      <Edit2 className="h-4 w-4" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={() => handleDelete(competitor.id)}
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                </div>
              </CardHeader>
              <CardContent>
                {competitor.website && (
                  <div className="flex items-center gap-2 text-sm text-muted-foreground mb-3">
                    <Globe className="h-3 w-3" />
                    <a 
                      href={competitor.website} 
                      target="_blank" 
                      rel="noopener noreferrer"
                      className="hover:underline"
                    >
                      {competitor.website}
                    </a>
                  </div>
                )}
                <div className="flex items-center justify-between">
                  <div className="text-sm text-muted-foreground">
                    {competitor.features?.length || 0} features tracked
                  </div>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => handleAnalyze(competitor.id)}
                    disabled={analyzingCompetitor === competitor.id}
                  >
                    <Sparkles className="mr-2 h-3 w-3" />
                    {analyzingCompetitor === competitor.id ? 'Analyzing...' : 'Analyze'}
                  </Button>
                </div>
                {competitor.company_size && (
                  <Badge variant="outline" className="mt-3">
                    {competitor.company_size}
                  </Badge>
                )}
              </CardContent>
            </Card>
          ))}
        </div>
      ) : (
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-12">
            <Building2 className="h-12 w-12 text-muted-foreground mb-4" />
            <p className="text-muted-foreground mb-4">No competitors found</p>
            <Button onClick={() => setIsCreateDialogOpen(true)}>
              Add Your First Competitor
            </Button>
          </CardContent>
        </Card>
      )}

      {/* Create/Edit Dialog */}
      <Dialog
        open={isCreateDialogOpen || !!editingCompetitor}
        onOpenChange={(open) => {
          if (!open) {
            setIsCreateDialogOpen(false);
            setEditingCompetitor(null);
            form.reset();
          }
        }}
      >
        <DialogContent className="sm:max-w-[525px]">
          <DialogHeader>
            <DialogTitle>
              {editingCompetitor ? 'Edit Competitor' : 'Add New Competitor'}
            </DialogTitle>
            <DialogDescription>
              Enter the competitor's information to track their features and positioning
            </DialogDescription>
          </DialogHeader>
          <Form {...form}>
            <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
              <FormField
                control={form.control}
                name="name"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Company Name</FormLabel>
                    <FormControl>
                      <Input placeholder="Competitor Inc." {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="website"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Website</FormLabel>
                    <FormControl>
                      <Input type="url" placeholder="https://example.com" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="market_position"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Market Position</FormLabel>
                    <Select onValueChange={field.onChange} defaultValue={field.value}>
                      <FormControl>
                        <SelectTrigger>
                          <SelectValue placeholder="Select market position" />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        <SelectItem value="Leader">Leader</SelectItem>
                        <SelectItem value="Challenger">Challenger</SelectItem>
                        <SelectItem value="Visionary">Visionary</SelectItem>
                        <SelectItem value="Niche">Niche</SelectItem>
                      </SelectContent>
                    </Select>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="company_size"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Company Size</FormLabel>
                    <Select onValueChange={field.onChange} defaultValue={field.value}>
                      <FormControl>
                        <SelectTrigger>
                          <SelectValue placeholder="Select company size" />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        <SelectItem value="Startup">Startup</SelectItem>
                        <SelectItem value="SMB">SMB</SelectItem>
                        <SelectItem value="Enterprise">Enterprise</SelectItem>
                        <SelectItem value="Large Enterprise">Large Enterprise</SelectItem>
                      </SelectContent>
                    </Select>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="funding_stage"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Funding Stage (Optional)</FormLabel>
                    <FormControl>
                      <Input placeholder="Series B, IPO, etc." {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <DialogFooter>
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => {
                    setIsCreateDialogOpen(false);
                    setEditingCompetitor(null);
                    form.reset();
                  }}
                >
                  Cancel
                </Button>
                <Button
                  type="submit"
                  disabled={createMutation.isPending || updateMutation.isPending}
                >
                  {createMutation.isPending || updateMutation.isPending
                    ? 'Saving...'
                    : editingCompetitor
                    ? 'Update'
                    : 'Add'}
                </Button>
              </DialogFooter>
            </form>
          </Form>
        </DialogContent>
      </Dialog>
    </div>
  );
}