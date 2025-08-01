import { useEffect } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import * as z from 'zod';
import { useUpdateFeature } from '@/hooks/useFeatures';
import { Feature } from '@/types';
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
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Button } from '@/components/ui/button';
import { Loader2 } from 'lucide-react';

const editFeatureSchema = z.object({
  title: z.string().min(1, 'Title is required').max(255),
  description: z.string().optional(),
});

type EditFeatureFormData = z.infer<typeof editFeatureSchema>;

interface EditFeatureDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  feature: Feature | null;
}

export function EditFeatureDialog({ open, onOpenChange, feature }: EditFeatureDialogProps) {
  const updateFeature = useUpdateFeature();
  
  const form = useForm<EditFeatureFormData>({
    resolver: zodResolver(editFeatureSchema),
    defaultValues: {
      title: '',
      description: '',
    },
  });

  // Update form values when feature changes
  useEffect(() => {
    if (feature) {
      form.reset({
        title: feature.title,
        description: feature.description || '',
      });
    }
  }, [feature, form]);

  const onSubmit = async (data: EditFeatureFormData) => {
    if (!feature) return;
    
    try {
      await updateFeature.mutateAsync({
        id: feature.id,
        data: {
          ...data,
          epic_id: feature.epic_id,
        },
      });
      onOpenChange(false);
    } catch (error) {
      // Error handling is done in the mutation hook
    }
  };

  if (!feature) return null;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[625px]">
        <DialogHeader>
          <DialogTitle>Edit Feature</DialogTitle>
          <DialogDescription>
            Update the feature details
          </DialogDescription>
        </DialogHeader>
        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
            <FormField
              control={form.control}
              name="title"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Title</FormLabel>
                  <FormControl>
                    <Input placeholder="Feature title" {...field} />
                  </FormControl>
                  <FormDescription>
                    A clear, concise title for the feature
                  </FormDescription>
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
                      placeholder="Describe the feature in detail..."
                      className="min-h-[100px]"
                      {...field}
                    />
                  </FormControl>
                  <FormDescription>
                    Detailed description of the feature's functionality and requirements
                  </FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />
            
            <DialogFooter>
              <Button
                type="button"
                variant="outline"
                onClick={() => onOpenChange(false)}
                disabled={updateFeature.isPending}
              >
                Cancel
              </Button>
              <Button type="submit" disabled={updateFeature.isPending}>
                {updateFeature.isPending && (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                )}
                Save Changes
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
}