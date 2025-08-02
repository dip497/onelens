import React, { useState, useEffect } from 'react';
import { Upload, X, FileSpreadsheet, AlertCircle } from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Alert, AlertDescription } from '@/components/ui/alert';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { useToast } from '@/components/ui/use-toast';
import api from '@/services/api';

interface RFPUploadDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSuccess: () => void;
}

export default function RFPUploadDialog({
  open,
  onOpenChange,
  onSuccess,
}: RFPUploadDialogProps) {
  const [file, setFile] = useState<File | null>(null);
  const [customerId, setCustomerId] = useState<string>('none');
  const [purpose, setPurpose] = useState<string>('');
  const [uploading, setUploading] = useState(false);
  const [dragActive, setDragActive] = useState(false);
  const [customers, setCustomers] = useState<any[]>([]);
  const [loadingCustomers, setLoadingCustomers] = useState(false);
  const { toast } = useToast();

  // Load customers when dialog opens
  useEffect(() => {
    if (open) {
      loadCustomers();
    }
  }, [open]);

  const loadCustomers = async () => {
    try {
      setLoadingCustomers(true);
      const response = await api.get('/customers?limit=100');
      setCustomers(response.data.items || []);
    } catch (error) {
      console.error('Failed to load customers:', error);
      toast({
        title: 'Warning',
        description: 'Failed to load customers. You can still upload without selecting a customer.',
        variant: 'destructive',
      });
    } finally {
      setLoadingCustomers(false);
    }
  };

  const handleDrag = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === 'dragenter' || e.type === 'dragover') {
      setDragActive(true);
    } else if (e.type === 'dragleave') {
      setDragActive(false);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);

    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleFile(e.dataTransfer.files[0]);
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      handleFile(e.target.files[0]);
    }
  };

  const handleFile = (file: File) => {
    const allowedTypes = [
      'application/vnd.ms-excel',
      'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      'application/pdf',
    ];

    if (!allowedTypes.includes(file.type)) {
      toast({
        title: 'Invalid file type',
        description: 'Please upload an Excel (.xlsx, .xls) or PDF file.',
        variant: 'destructive',
      });
      return;
    }

    setFile(file);
  };

  const handleUpload = async () => {
    if (!file) {
      toast({
        title: 'No file selected',
        description: 'Please select a file to upload.',
        variant: 'destructive',
      });
      return;
    }

    if (!purpose) {
      toast({
        title: 'Purpose not selected',
        description: 'Please select what you want to do with this RFP.',
        variant: 'destructive',
      });
      return;
    }

    setUploading(true);

    const formData = new FormData();
    formData.append('file', file);
    formData.append('purpose', purpose);
    if (customerId && customerId !== 'none') {
      formData.append('customer_id', customerId);
    }

    try {
      await api.post('/rfp/upload', formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      });

      toast({
        title: 'Upload successful',
        description: 'Your RFP document is being processed.',
      });

      onSuccess();
      resetForm();
    } catch (error: any) {
      toast({
        title: 'Upload failed',
        description: error.response?.data?.detail || 'Failed to upload file.',
        variant: 'destructive',
      });
    } finally {
      setUploading(false);
    }
  };

  const resetForm = () => {
    setFile(null);
    setCustomerId('none');
    setPurpose('');
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Upload RFP Document</DialogTitle>
          <DialogDescription>
            Upload an Excel or PDF file containing RFP questions and answers.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          {/* File Upload Area */}
          <div
            className={`
              border-2 border-dashed rounded-lg p-6 text-center cursor-pointer
              transition-colors duration-200
              ${dragActive ? 'border-primary bg-primary/5' : 'border-muted-foreground/25'}
              ${file ? 'bg-muted/50' : 'hover:border-primary/50'}
            `}
            onDragEnter={handleDrag}
            onDragLeave={handleDrag}
            onDragOver={handleDrag}
            onDrop={handleDrop}
            onClick={() => document.getElementById('file-upload')?.click()}
          >
            <input
              id="file-upload"
              type="file"
              className="hidden"
              accept=".xlsx,.xls,.pdf"
              onChange={handleFileChange}
            />

            {file ? (
              <div className="flex items-center justify-center gap-2">
                <FileSpreadsheet className="h-8 w-8 text-primary" />
                <div className="text-left">
                  <p className="font-medium">{file.name}</p>
                  <p className="text-sm text-muted-foreground">
                    {(file.size / 1024 / 1024).toFixed(2)} MB
                  </p>
                </div>
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={(e) => {
                    e.stopPropagation();
                    setFile(null);
                  }}
                >
                  <X className="h-4 w-4" />
                </Button>
              </div>
            ) : (
              <>
                <Upload className="h-8 w-8 mx-auto mb-2 text-muted-foreground" />
                <p className="text-sm font-medium">
                  Click to upload or drag and drop
                </p>
                <p className="text-xs text-muted-foreground">
                  Excel (.xlsx, .xls) or PDF files
                </p>
              </>
            )}
          </div>

          {/* Customer Selection */}
          <div className="space-y-2">
            <Label htmlFor="customer">Customer (Optional)</Label>
            <Select value={customerId} onValueChange={setCustomerId}>
              <SelectTrigger>
                <SelectValue placeholder={loadingCustomers ? "Loading customers..." : "Select a customer"} />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="none">No customer</SelectItem>
                {customers.map((customer) => (
                  <SelectItem key={customer.id} value={customer.id}>
                    <div className="flex items-center gap-2">
                      <span className="font-medium">{customer.name}</span>
                      {customer.company && (
                        <span className="text-xs text-muted-foreground">({customer.company})</span>
                      )}
                    </div>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Purpose Selection */}
          <div className="space-y-2">
            <Label htmlFor="purpose">What do you want to do with this RFP?</Label>
            <Select value={purpose} onValueChange={setPurpose}>
              <SelectTrigger>
                <SelectValue placeholder="Choose your purpose" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="analyze">
                  <div className="flex items-center gap-2">
                    <span>📋</span>
                    <div>
                      <div className="font-medium">Analyze RFP Content</div>
                      <div className="text-xs text-muted-foreground">Extract and review Q&A pairs, analyze features</div>
                    </div>
                  </div>
                </SelectItem>
                <SelectItem value="respond">
                  <div className="flex items-center gap-2">
                    <span>🤖</span>
                    <div>
                      <div className="font-medium">Generate RFP Response</div>
                      <div className="text-xs text-muted-foreground">Create professional responses using AI + knowledge base</div>
                    </div>
                  </div>
                </SelectItem>
              </SelectContent>
            </Select>
          </div>

          {/* Info Alert */}
          <Alert>
            <AlertCircle className="h-4 w-4" />
            <AlertDescription>
              {purpose === 'analyze'
                ? 'Your file should contain questions and answers in a structured format. For Excel files, use "Question" and "Answer" columns.'
                : purpose === 'respond'
                ? 'Your file should contain questions that need professional responses. The AI will generate answers using your knowledge base.'
                : 'Select a purpose above to see specific file format requirements.'
              }
            </AlertDescription>
          </Alert>

          {/* Actions */}
          <div className="flex justify-end gap-2">
            <Button
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={uploading}
            >
              Cancel
            </Button>
            <Button onClick={handleUpload} disabled={!file || !purpose || uploading}>
              {uploading ? 'Uploading...' : 'Upload'}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}