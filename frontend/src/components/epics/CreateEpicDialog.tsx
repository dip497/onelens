import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import * as z from 'zod';
import { useCreateEpic } from '@/hooks/useEpics';
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

const createEpicSchema = z.object({
  title: z.string().min(1, 'Title is required').max(255),
  description: z.string().optional(),
  business_justification: z.string().optional(),
});

type CreateEpicFormData = z.infer<typeof createEpicSchema>;

interface CreateEpicDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function CreateEpicDialog({ open, onOpenChange }: CreateEpicDialogProps) {
  const createEpic = useCreateEpic();
  
  const form = useForm<CreateEpicFormData>({
    resolver: zodResolver(createEpicSchema),
    defaultValues: {
      title: '',
      description: '',
      business_justification: '',
    },
  });

  const onSubmit = async (data: CreateEpicFormData) => {
    try {
      await createEpic.mutateAsync(data);
      form.reset();
      onOpenChange(false);
    } catch (error) {
      // Error handling is done in the mutation hook
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[625px]">
        <DialogHeader>
          <DialogTitle>Create New Epic</DialogTitle>
          <DialogDescription>
            Create a new epic to organize and analyze related features.
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
                    <Input placeholder="Epic title" {...field} />
                  </FormControl>
                  <FormDescription>
                    A clear, concise title for your epic
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
                      placeholder="Describe the epic's goals and scope..."
                      className="min-h-[100px]"
                      {...field}
                    />
                  </FormControl>
                  <FormDescription>
                    Detailed description of what this epic aims to achieve
                  </FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />
            
            <FormField
              control={form.control}
              name="business_justification"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Business Justification</FormLabel>
                  <FormControl>
                    <Textarea
                      placeholder="Explain the business value and impact..."
                      className="min-h-[100px]"
                      {...field}
                    />
                  </FormControl>
                  <FormDescription>
                    Why is this epic important for the business?
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
                disabled={createEpic.isPending}
              >
                Cancel
              </Button>
              <Button type="submit" disabled={createEpic.isPending}>
                {createEpic.isPending && (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                )}
                Create Epic
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
}