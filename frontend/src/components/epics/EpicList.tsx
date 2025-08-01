import { format } from 'date-fns';
import { MoreHorizontal, Edit, Trash2, PlayCircle, Eye } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { Epic, EpicStatus } from '@/types';
import { useDeleteEpic, useAnalyzeEpic } from '@/hooks/useEpics';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  Pagination,
  PaginationContent,
  PaginationItem,
  PaginationLink,
  PaginationNext,
  PaginationPrevious,
} from '@/components/ui/pagination';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { useState } from 'react';

interface EpicListProps {
  epics: Epic[];
  total: number;
  page: number;
  pageSize: number;
  onPageChange: (page: number) => void;
}

export function EpicList({ epics, total, page, pageSize, onPageChange }: EpicListProps) {
  const navigate = useNavigate();
  const deleteEpic = useDeleteEpic();
  const analyzeEpic = useAnalyzeEpic();
  const [deleteTarget, setDeleteTarget] = useState<Epic | null>(null);

  const totalPages = Math.ceil(total / pageSize);

  const getStatusBadge = (status: EpicStatus) => {
    const variants: Record<EpicStatus, string> = {
      [EpicStatus.DRAFT]: 'secondary',
      [EpicStatus.ANALYSIS_PENDING]: 'warning',
      [EpicStatus.ANALYZED]: 'default',
      [EpicStatus.APPROVED]: 'success',
      [EpicStatus.IN_PROGRESS]: 'primary',
      [EpicStatus.DELIVERED]: 'success',
    };

    return (
      <Badge variant={variants[status] as any}>
        {status}
      </Badge>
    );
  };

  const handleDelete = async () => {
    if (deleteTarget) {
      await deleteEpic.mutateAsync(deleteTarget.id);
      setDeleteTarget(null);
    }
  };

  const handleAnalyze = async (epicId: string) => {
    await analyzeEpic.mutateAsync(epicId);
  };

  if (epics.length === 0) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        No epics found. Create your first epic to get started.
      </div>
    );
  }


  return (
    <div className="space-y-4">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Title</TableHead>
            <TableHead>Status</TableHead>
            <TableHead>Features</TableHead>
            <TableHead>Created</TableHead>
            <TableHead className="text-right">Actions</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {epics.map((epic) => (
            <TableRow key={epic.id} className="cursor-pointer" onClick={() => navigate(`/epics/${epic.id}`)}>
              <TableCell className="font-medium">
                <div>
                  <div className="font-semibold">{epic.title}</div>
                  {epic.description && (
                    <div className="text-sm text-muted-foreground line-clamp-1">
                      {epic.description}
                    </div>
                  )}
                </div>
              </TableCell>
              <TableCell>{getStatusBadge(epic.status)}</TableCell>
              <TableCell>
                <Badge variant="outline">
                  {epic.features_count || 0} features
                </Badge>
              </TableCell>
              <TableCell>{format(new Date(epic.created_at), 'MMM dd, yyyy')}</TableCell>
              <TableCell className="text-right">
                <DropdownMenu>
                  <DropdownMenuTrigger asChild onClick={(e) => e.stopPropagation()}>
                    <Button variant="ghost" className="h-8 w-8 p-0">
                      <span className="sr-only">Open menu</span>
                      <MoreHorizontal className="h-4 w-4" />
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end">
                    <DropdownMenuLabel>Actions</DropdownMenuLabel>
                    <DropdownMenuItem onClick={(e) => {
                      e.stopPropagation();
                      navigate(`/epics/${epic.id}`);
                    }}>
                      <Eye className="mr-2 h-4 w-4" />
                      View Details
                    </DropdownMenuItem>
                    <DropdownMenuItem onClick={(e) => {
                      e.stopPropagation();
                      navigate(`/epics/${epic.id}/edit`);
                    }}>
                      <Edit className="mr-2 h-4 w-4" />
                      Edit
                    </DropdownMenuItem>
                    {epic.status === EpicStatus.DRAFT && (
                      <DropdownMenuItem onClick={(e) => {
                        e.stopPropagation();
                        handleAnalyze(epic.id);
                      }}>
                        <PlayCircle className="mr-2 h-4 w-4" />
                        Start Analysis
                      </DropdownMenuItem>
                    )}
                    <DropdownMenuSeparator />
                    <DropdownMenuItem
                      className="text-destructive"
                      onClick={(e) => {
                        e.stopPropagation();
                        setDeleteTarget(epic);
                      }}
                    >
                      <Trash2 className="mr-2 h-4 w-4" />
                      Delete
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>

      {/* Pagination */}
      {totalPages > 1 && (
        <Pagination>
          <PaginationContent>
            <PaginationItem>
              <PaginationPrevious
                onClick={() => onPageChange(page - 1)}
                className={page === 1 ? 'pointer-events-none opacity-50' : 'cursor-pointer'}
              />
            </PaginationItem>
            {Array.from({ length: totalPages }, (_, i) => i + 1).map((pageNum) => (
              <PaginationItem key={pageNum}>
                <PaginationLink
                  onClick={() => onPageChange(pageNum)}
                  isActive={pageNum === page}
                  className="cursor-pointer"
                >
                  {pageNum}
                </PaginationLink>
              </PaginationItem>
            ))}
            <PaginationItem>
              <PaginationNext
                onClick={() => onPageChange(page + 1)}
                className={page === totalPages ? 'pointer-events-none opacity-50' : 'cursor-pointer'}
              />
            </PaginationItem>
          </PaginationContent>
        </Pagination>
      )}

      {/* Delete Confirmation Dialog */}
      <AlertDialog open={!!deleteTarget} onOpenChange={() => setDeleteTarget(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Are you sure?</AlertDialogTitle>
            <AlertDialogDescription>
              This will permanently delete the epic "{deleteTarget?.title}" and all its features.
              This action cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={handleDelete} className="bg-destructive text-destructive-foreground">
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}