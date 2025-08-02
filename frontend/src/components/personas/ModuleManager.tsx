import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Plus, Edit2, Trash2, GripVertical, Package } from 'lucide-react';
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
import { Badge } from '@/components/ui/badge';
import { productsApi } from '@/lib/api/products';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';

const moduleFormSchema = z.object({
  name: z.string().min(1, 'Name is required'),
  description: z.string().optional(),
  icon: z.string().optional(),
  order_index: z.number().min(0).default(0),
});

type ModuleFormValues = z.infer<typeof moduleFormSchema>;

interface ModuleManagerProps {
  productId: string;
}

export function ModuleManager({ productId }: ModuleManagerProps) {
  const queryClient = useQueryClient();
  const [isCreateDialogOpen, setIsCreateDialogOpen] = useState(false);
  const [editingModule, setEditingModule] = useState<any>(null);
  const [isDragging, setIsDragging] = useState(false);

  const { data: modules, isLoading } = useQuery({
    queryKey: ['product-modules', productId],
    queryFn: () => productsApi.getProductModules(productId),
  });

  const form = useForm<ModuleFormValues>({
    resolver: zodResolver(moduleFormSchema),
    defaultValues: {
      name: '',
      description: '',
      icon: '',
      order_index: 0,
    },
  });

  const createMutation = useMutation({
    mutationFn: (data: ModuleFormValues) =>
      productsApi.createProductModule(productId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['product-modules', productId] });
      toast.success('Module created successfully');
      setIsCreateDialogOpen(false);
      form.reset();
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to create module');
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: ModuleFormValues }) =>
      productsApi.updateModule(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['product-modules', productId] });
      toast.success('Module updated successfully');
      setEditingModule(null);
      form.reset();
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to update module');
    },
  });

  const deleteMutation = useMutation({
    mutationFn: productsApi.deleteModule,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['product-modules', productId] });
      toast.success('Module deleted successfully');
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to delete module');
    },
  });

  const reorderMutation = useMutation({
    mutationFn: (moduleOrders: Array<{ id: string; order_index: number }>) =>
      productsApi.reorderModules(productId, moduleOrders),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['product-modules', productId] });
      toast.success('Modules reordered successfully');
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to reorder modules');
    },
  });

  const handleEdit = (module: any) => {
    setEditingModule(module);
    form.reset({
      name: module.name,
      description: module.description || '',
      icon: module.icon || '',
      order_index: module.order_index,
    });
  };

  const handleDelete = (moduleId: string) => {
    if (confirm('Are you sure you want to delete this module? This will not delete the features, but they will be unassigned from this module.')) {
      deleteMutation.mutate(moduleId);
    }
  };

  const onSubmit = (values: ModuleFormValues) => {
    if (editingModule) {
      updateMutation.mutate({ id: editingModule.id, data: values });
    } else {
      // Set order_index to be at the end
      const maxIndex = modules?.reduce((max, m) => Math.max(max, m.order_index), -1) ?? -1;
      createMutation.mutate({ ...values, order_index: maxIndex + 1 });
    }
  };

  const handleDragStart = (e: React.DragEvent, moduleId: string, index: number) => {
    e.dataTransfer.setData('moduleId', moduleId);
    e.dataTransfer.setData('sourceIndex', index.toString());
    setIsDragging(true);
  };

  const handleDragEnd = () => {
    setIsDragging(false);
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
  };

  const handleDrop = (e: React.DragEvent, targetIndex: number) => {
    e.preventDefault();
    const sourceIndex = parseInt(e.dataTransfer.getData('sourceIndex'));
    
    if (sourceIndex !== targetIndex && modules) {
      const newModules = [...modules];
      const [movedModule] = newModules.splice(sourceIndex, 1);
      newModules.splice(targetIndex, 0, movedModule);
      
      const moduleOrders = newModules.map((module, index) => ({
        id: module.id,
        order_index: index,
      }));
      
      reorderMutation.mutate(moduleOrders);
    }
    setIsDragging(false);
  };

  if (isLoading) {
    return <div>Loading modules...</div>;
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold">Product Modules</h2>
          <p className="text-muted-foreground">
            Organize your features into logical modules
          </p>
        </div>
        <Button onClick={() => setIsCreateDialogOpen(true)}>
          <Plus className="mr-2 h-4 w-4" />
          Add Module
        </Button>
      </div>

      {modules && modules.length === 0 ? (
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-12">
            <Package className="h-12 w-12 text-muted-foreground mb-4" />
            <p className="text-muted-foreground mb-4">No modules defined yet</p>
            <Button onClick={() => setIsCreateDialogOpen(true)}>
              Create Your First Module
            </Button>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-4">
          {modules?.map((module, index) => (
            <Card
              key={module.id}
              className={`${isDragging ? 'cursor-move' : ''}`}
              draggable
              onDragStart={(e) => handleDragStart(e, module.id, index)}
              onDragEnd={handleDragEnd}
              onDragOver={handleDragOver}
              onDrop={(e) => handleDrop(e, index)}
            >
              <CardHeader>
                <div className="flex items-start justify-between">
                  <div className="flex items-center gap-3">
                    <GripVertical className="h-5 w-5 text-muted-foreground cursor-move" />
                    <div>
                      <CardTitle className="text-lg flex items-center gap-2">
                        {module.icon && <span>{module.icon}</span>}
                        {module.name}
                      </CardTitle>
                      <Badge variant="secondary" className="mt-1">
                        {module.feature_count || 0} features
                      </Badge>
                    </div>
                  </div>
                  <div className="flex items-center gap-1">
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={() => handleEdit(module)}
                    >
                      <Edit2 className="h-4 w-4" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={() => handleDelete(module.id)}
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                </div>
              </CardHeader>
              {module.description && (
                <CardContent>
                  <p className="text-sm text-muted-foreground">
                    {module.description}
                  </p>
                </CardContent>
              )}
            </Card>
          ))}
        </div>
      )}

      {/* Create/Edit Dialog */}
      <Dialog
        open={isCreateDialogOpen || !!editingModule}
        onOpenChange={(open) => {
          if (!open) {
            setIsCreateDialogOpen(false);
            setEditingModule(null);
            form.reset();
          }
        }}
      >
        <DialogContent className="sm:max-w-[525px]">
          <DialogHeader>
            <DialogTitle>
              {editingModule ? 'Edit Module' : 'Create New Module'}
            </DialogTitle>
            <DialogDescription>
              Define a module to group related features
            </DialogDescription>
          </DialogHeader>
          <Form {...form}>
            <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
              <FormField
                control={form.control}
                name="name"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Module Name</FormLabel>
                    <FormControl>
                      <Input placeholder="Core Features" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="icon"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Icon (Emoji)</FormLabel>
                    <FormControl>
                      <Input placeholder="📦" maxLength={2} {...field} />
                    </FormControl>
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
                        placeholder="Describe what features belong in this module..."
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
                    setEditingModule(null);
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
                    : editingModule
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