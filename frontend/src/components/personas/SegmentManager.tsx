import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Plus, Edit2, Trash2 } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
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
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Badge } from '@/components/ui/badge';
import { productsApi } from '@/lib/api/products';
import { CustomerSize } from '@/types/product';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';

const segmentFormSchema = z.object({
  name: z.string().min(1, 'Name is required'),
  description: z.string().optional(),
  target_market: z.string().optional(),
  customer_size: z.nativeEnum(CustomerSize).optional(),
});

type SegmentFormValues = z.infer<typeof segmentFormSchema>;

interface SegmentManagerProps {
  productId: string;
}

export function SegmentManager({ productId }: SegmentManagerProps) {
  const queryClient = useQueryClient();
  const [isCreateDialogOpen, setIsCreateDialogOpen] = useState(false);
  const [editingSegment, setEditingSegment] = useState<any>(null);

  const { data: segments, isLoading } = useQuery({
    queryKey: ['product-segments', productId],
    queryFn: () => productsApi.getProductSegments(productId),
  });

  const form = useForm<SegmentFormValues>({
    resolver: zodResolver(segmentFormSchema),
    defaultValues: {
      name: '',
      description: '',
      target_market: '',
      customer_size: undefined,
    },
  });

  const createMutation = useMutation({
    mutationFn: (data: SegmentFormValues) =>
      productsApi.createProductSegment(productId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['product-segments', productId] });
      toast.success('Segment created successfully');
      setIsCreateDialogOpen(false);
      form.reset();
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to create segment');
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: SegmentFormValues }) =>
      productsApi.updateSegment(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['product-segments', productId] });
      toast.success('Segment updated successfully');
      setEditingSegment(null);
      form.reset();
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to update segment');
    },
  });

  const deleteMutation = useMutation({
    mutationFn: productsApi.deleteSegment,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['product-segments', productId] });
      toast.success('Segment deleted successfully');
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to delete segment');
    },
  });

  const handleEdit = (segment: any) => {
    setEditingSegment(segment);
    form.reset({
      name: segment.name,
      description: segment.description || '',
      target_market: segment.target_market || '',
      customer_size: segment.customer_size,
    });
  };

  const handleDelete = (segmentId: string) => {
    if (confirm('Are you sure you want to delete this segment?')) {
      deleteMutation.mutate(segmentId);
    }
  };

  const onSubmit = (values: SegmentFormValues) => {
    if (editingSegment) {
      updateMutation.mutate({ id: editingSegment.id, data: values });
    } else {
      createMutation.mutate(values);
    }
  };

  if (isLoading) {
    return <div>Loading segments...</div>;
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold">Customer Segments</h2>
          <p className="text-muted-foreground">
            Define and manage your target customer segments
          </p>
        </div>
        <Button onClick={() => setIsCreateDialogOpen(true)}>
          <Plus className="mr-2 h-4 w-4" />
          Add Segment
        </Button>
      </div>

      {segments && segments.length === 0 ? (
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-12">
            <p className="text-muted-foreground mb-4">No segments defined yet</p>
            <Button onClick={() => setIsCreateDialogOpen(true)}>
              Create Your First Segment
            </Button>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          {segments?.map((segment) => (
            <Card key={segment.id}>
              <CardHeader>
                <div className="flex items-start justify-between">
                  <div>
                    <CardTitle className="text-lg">{segment.name}</CardTitle>
                    {segment.customer_size && (
                      <Badge variant="outline" className="mt-2">
                        {segment.customer_size}
                      </Badge>
                    )}
                  </div>
                  <div className="flex items-center gap-1">
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={() => handleEdit(segment)}
                    >
                      <Edit2 className="h-4 w-4" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={() => handleDelete(segment.id)}
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                </div>
              </CardHeader>
              <CardContent>
                {segment.description && (
                  <p className="text-sm text-muted-foreground mb-3">
                    {segment.description}
                  </p>
                )}
                {segment.target_market && (
                  <div>
                    <p className="text-sm font-medium">Target Market</p>
                    <p className="text-sm text-muted-foreground">
                      {segment.target_market}
                    </p>
                  </div>
                )}
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Create/Edit Dialog */}
      <Dialog
        open={isCreateDialogOpen || !!editingSegment}
        onOpenChange={(open) => {
          if (!open) {
            setIsCreateDialogOpen(false);
            setEditingSegment(null);
            form.reset();
          }
        }}
      >
        <DialogContent className="sm:max-w-[525px]">
          <DialogHeader>
            <DialogTitle>
              {editingSegment ? 'Edit Segment' : 'Create New Segment'}
            </DialogTitle>
            <DialogDescription>
              Define the characteristics of this customer segment
            </DialogDescription>
          </DialogHeader>
          <Form {...form}>
            <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
              <FormField
                control={form.control}
                name="name"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Segment Name</FormLabel>
                    <FormControl>
                      <Input placeholder="Enterprise Customers" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="customer_size"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Customer Size</FormLabel>
                    <Select
                      onValueChange={field.onChange}
                      defaultValue={field.value}
                    >
                      <FormControl>
                        <SelectTrigger>
                          <SelectValue placeholder="Select customer size" />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        <SelectItem value={CustomerSize.SMB}>SMB</SelectItem>
                        <SelectItem value={CustomerSize.MID_MARKET}>
                          Mid Market
                        </SelectItem>
                        <SelectItem value={CustomerSize.ENTERPRISE}>
                          Enterprise
                        </SelectItem>
                        <SelectItem value={CustomerSize.ALL}>All</SelectItem>
                      </SelectContent>
                    </Select>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="description"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Description</FormLabel>
                    <FormControl>
                      <Textarea
                        placeholder="Describe this customer segment..."
                        className="resize-none"
                        {...field}
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="target_market"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Target Market</FormLabel>
                    <FormControl>
                      <Textarea
                        placeholder="Define the target market characteristics..."
                        className="resize-none"
                        {...field}
                      />
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
                    setEditingSegment(null);
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
                    : editingSegment
                    ? 'Update'
                    : 'Create'}
                </Button>
              </DialogFooter>
            </form>
          </Form>
        </DialogContent>
      </Dialog>
    </div>
  );
}