import React, { useState, useEffect } from 'react';
import { Upload, FileText, CheckCircle, AlertCircle, Clock, Search, Filter } from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { useToast } from '@/components/ui/use-toast';
import RFPUploadDialog from './RFPUploadDialog';
import RFPDetailDialog from './RFPDetailDialog';
import api from '@/services/api';

interface RFPDocument {
  id: string;
  filename: string;
  customer_id?: string;
  processed_status: 'Pending' | 'Processing' | 'Complete' | 'Failed';
  total_questions?: number;
  processed_questions?: number;
  business_context?: any;
  created_at: string;
  updated_at: string;
}

export default function RFPDashboard() {
  const [documents, setDocuments] = useState<RFPDocument[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploadDialogOpen, setUploadDialogOpen] = useState(false);
  const [selectedDocument, setSelectedDocument] = useState<RFPDocument | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const { toast } = useToast();

  useEffect(() => {
    fetchDocuments();
    // Poll for updates every 5 seconds
    const interval = setInterval(fetchDocuments, 5000);
    return () => clearInterval(interval);
  }, []);

  const fetchDocuments = async () => {
    try {
      const response = await api.get('/rfp');
      setDocuments(response.data.items);
    } catch (error) {
      toast({
        title: 'Error',
        description: 'Failed to fetch RFP documents',
        variant: 'destructive',
      });
    } finally {
      setLoading(false);
    }
  };

  const handleUploadSuccess = () => {
    fetchDocuments();
    setUploadDialogOpen(false);
    toast({
      title: 'Success',
      description: 'RFP document uploaded successfully',
    });
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'complete':
        return <CheckCircle className="h-4 w-4 text-green-500" />;
      case 'processing':
        return <Clock className="h-4 w-4 text-blue-500 animate-spin" />;
      case 'failed':
        return <AlertCircle className="h-4 w-4 text-red-500" />;
      default:
        return <Clock className="h-4 w-4 text-gray-500" />;
    }
  };

  const getProcessingProgress = (doc: RFPDocument) => {
    if (!doc.total_questions || doc.total_questions === 0) return 0;
    return ((doc.processed_questions || 0) / doc.total_questions) * 100;
  };

  const filteredDocuments = documents.filter((doc) => {
    const matchesSearch = doc.filename.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesStatus = statusFilter === 'all' || doc.processed_status === statusFilter;
    return matchesSearch && matchesStatus;
  });

  // Summary statistics
  const stats = {
    total: documents.length,
    complete: documents.filter((d) => d.processed_status === 'Complete').length,
    processing: documents.filter((d) => d.processed_status === 'Processing').length,
    failed: documents.filter((d) => d.processed_status === 'Failed').length,
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-2xl font-bold">RFP Analyzer</h1>
          <p className="text-muted-foreground">
            Upload and analyze RFP documents to identify feature requirements
          </p>
        </div>
        <Button onClick={() => setUploadDialogOpen(true)}>
          <Upload className="mr-2 h-4 w-4" />
          Upload RFP
        </Button>
      </div>

      {/* Statistics Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">Total Documents</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{stats.total}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">Completed</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-green-600">{stats.complete}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">Processing</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-blue-600">{stats.processing}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">Failed</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-red-600">{stats.failed}</div>
          </CardContent>
        </Card>
      </div>

      {/* Documents Table */}
      <Card>
        <CardHeader>
          <div className="flex justify-between items-center">
            <CardTitle>RFP Documents</CardTitle>
            <div className="flex gap-2">
              <div className="relative">
                <Search className="absolute left-2 top-2.5 h-4 w-4 text-muted-foreground" />
                <Input
                  placeholder="Search documents..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="pl-8 w-64"
                />
              </div>
              <Select value={statusFilter} onValueChange={setStatusFilter}>
                <SelectTrigger className="w-32">
                  <SelectValue placeholder="Status" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Status</SelectItem>
                  <SelectItem value="Pending">Pending</SelectItem>
                  <SelectItem value="Processing">Processing</SelectItem>
                  <SelectItem value="Complete">Complete</SelectItem>
                  <SelectItem value="Failed">Failed</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Document Name</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Questions</TableHead>
                <TableHead>Progress</TableHead>
                <TableHead>Uploaded</TableHead>
                <TableHead>Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filteredDocuments.map((doc) => (
                <TableRow key={doc.id}>
                  <TableCell className="font-medium">
                    <div className="flex items-center gap-2">
                      <FileText className="h-4 w-4 text-muted-foreground" />
                      {doc.filename}
                    </div>
                  </TableCell>
                  <TableCell>
                    <div className="flex items-center gap-2">
                      {getStatusIcon(doc.processed_status)}
                      <Badge
                        variant={
                          doc.processed_status === 'Complete'
                            ? 'success'
                            : doc.processed_status === 'Failed'
                            ? 'destructive'
                            : 'secondary'
                        }
                      >
                        {doc.processed_status}
                      </Badge>
                    </div>
                  </TableCell>
                  <TableCell>
                    {doc.total_questions || '-'}
                  </TableCell>
                  <TableCell>
                    {doc.processed_status === 'processing' && doc.total_questions ? (
                      <div className="w-32">
                        <Progress value={getProcessingProgress(doc)} className="h-2" />
                        <span className="text-xs text-muted-foreground">
                          {doc.processed_questions}/{doc.total_questions}
                        </span>
                      </div>
                    ) : (
                      '-'
                    )}
                  </TableCell>
                  <TableCell>
                    {new Date(doc.created_at).toLocaleDateString()}
                  </TableCell>
                  <TableCell>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => setSelectedDocument(doc)}
                      disabled={doc.processed_status !== 'Complete'}
                    >
                      View Details
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {/* Dialogs */}
      <RFPUploadDialog
        open={uploadDialogOpen}
        onOpenChange={setUploadDialogOpen}
        onSuccess={handleUploadSuccess}
      />

      {selectedDocument && (
        <RFPDetailDialog
          document={selectedDocument}
          open={!!selectedDocument}
          onOpenChange={(open) => !open && setSelectedDocument(null)}
        />
      )}
    </div>
  );
}