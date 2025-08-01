import { useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import * as z from 'zod';
import { ArrowLeft, Loader2 } from 'lucide-react';
import { useEpic, useUpdateEpic } from '@/hooks/useEpics';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Skeleton } from '@/components/ui/skeleton';
import { EpicStatus } from '@/types';

const editEpicSchema = z.object({
  title: z.string().min(1, 'Title is required').max(255),
  description: z.string().optional(),
  business_justification: z.string().optional(),
  status: z.nativeEnum(EpicStatus),
});

type EditEpicFormData = z.infer<typeof editEpicSchema>;

export function EditEpic() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { data: epic, isLoading } = useEpic(id!);
  const updateEpic = useUpdateEpic();

  const form = useForm<EditEpicFormData>({
    resolver: zodResolver(editEpicSchema),
    defaultValues: {
      title: '',
      description: '',
      business_justification: '',
      status: EpicStatus.DRAFT,
    },
  });

  // Update form values when epic data is loaded
  useEffect(() => {
    if (epic) {
      form.reset({
        title: epic.title,
        description: epic.description || '',
        business_justification: epic.business_justification || '',
        status: epic.status,
      });
    }
  }, [epic, form]);

  const onSubmit = async (data: EditEpicFormData) => {
    try {
      await updateEpic.mutateAsync({ id: id!, data });
      navigate(`/epics/${id}`);
    } catch (error) {
      // Error handling is done in the mutation hook
    }
  };

  if (isLoading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-12 w-1/3" />
        <Skeleton className="h-96 w-full" />
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

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center gap-4">
        <Button variant="ghost" size="icon" onClick={() => navigate(`/epics/${id}`)}>
          <ArrowLeft className="h-4 w-4" />
        </Button>
        <div>
          <h1 className="text-3xl font-bold">Edit Epic</h1>
          <p className="text-muted-foreground">Update epic details and status</p>
        </div>
      </div>

      {/* Form */}
      <Card>
        <CardHeader>
          <CardTitle>Epic Details</CardTitle>
          <CardDescription>
            Update the epic information and status
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Form {...form}>
            <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-6">
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

              <FormField
                control={form.control}
                name="status"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Status</FormLabel>
                    <Select onValueChange={field.onChange} value={field.value}>
                      <FormControl>
                        <SelectTrigger>
                          <SelectValue placeholder="Select a status" />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        <SelectItem value={EpicStatus.DRAFT}>Draft</SelectItem>
                        <SelectItem value={EpicStatus.ANALYSIS_PENDING}>Analysis Pending</SelectItem>
                        <SelectItem value={EpicStatus.ANALYZED}>Analyzed</SelectItem>
                        <SelectItem value={EpicStatus.APPROVED}>Approved</SelectItem>
                        <SelectItem value={EpicStatus.IN_PROGRESS}>In Progress</SelectItem>
                        <SelectItem value={EpicStatus.DELIVERED}>Delivered</SelectItem>
                      </SelectContent>
                    </Select>
                    <FormDescription>
                      Current status of the epic
                    </FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <div className="flex gap-4">
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => navigate(`/epics/${id}`)}
                  disabled={updateEpic.isPending}
                >
                  Cancel
                </Button>
                <Button type="submit" disabled={updateEpic.isPending}>
                  {updateEpic.isPending && (
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  )}
                  Save Changes
                </Button>
              </div>
            </form>
          </Form>
        </CardContent>
      </Card>
    </div>
  );
}