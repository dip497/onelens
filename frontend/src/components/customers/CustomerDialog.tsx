import React, { useState, useEffect } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { useToast } from '@/components/ui/use-toast';
import api from '@/services/api';

interface Customer {
  id: string;
  name: string;
  email?: string;
  company?: string;
  phone?: string;
  t_shirt_size?: string;
  segment?: string;
  vertical?: string;
  arr?: number;
  employee_count?: number;
  geographic_region?: string;
  strategic_importance?: string;
  created_at: string;
  updated_at: string;
}

interface CustomerDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  customer?: Customer | null;
  onSuccess: () => void;
}

const T_SHIRT_SIZES = ['XS', 'S', 'M', 'L', 'XL', 'XXL'];
const SEGMENTS = ['Small', 'Medium', 'Large', 'Enterprise'];
const VERTICALS = ['Healthcare', 'Finance', 'Technology', 'Manufacturing', 'Retail', 'Other'];
const IMPORTANCE_LEVELS = ['High', 'Medium', 'Low'];

export default function CustomerDialog({
  open,
  onOpenChange,
  customer,
  onSuccess,
}: CustomerDialogProps) {
  const [formData, setFormData] = useState({
    name: '',
    email: '',
    company: '',
    phone: '',
    t_shirt_size: '',
    segment: '',
    vertical: '',
    arr: '',
    employee_count: '',
    geographic_region: '',
    strategic_importance: '',
  });
  const [loading, setLoading] = useState(false);
  const { toast } = useToast();

  useEffect(() => {
    if (customer) {
      setFormData({
        name: customer.name || '',
        email: customer.email || '',
        company: customer.company || '',
        phone: customer.phone || '',
        t_shirt_size: customer.t_shirt_size || '',
        segment: customer.segment || '',
        vertical: customer.vertical || '',
        arr: customer.arr?.toString() || '',
        employee_count: customer.employee_count?.toString() || '',
        geographic_region: customer.geographic_region || '',
        strategic_importance: customer.strategic_importance || '',
      });
    } else {
      setFormData({
        name: '',
        email: '',
        company: '',
        phone: '',
        t_shirt_size: '',
        segment: '',
        vertical: '',
        arr: '',
        employee_count: '',
        geographic_region: '',
        strategic_importance: '',
      });
    }
  }, [customer, open]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);

    try {
      const payload = {
        ...formData,
        arr: formData.arr ? parseFloat(formData.arr) : undefined,
        employee_count: formData.employee_count ? parseInt(formData.employee_count) : undefined,
      };

      // Remove empty strings
      Object.keys(payload).forEach(key => {
        if (payload[key as keyof typeof payload] === '') {
          delete payload[key as keyof typeof payload];
        }
      });

      if (customer) {
        await api.put(`/customers/${customer.id}`, payload);
        toast({
          title: 'Success',
          description: 'Customer updated successfully',
        });
      } else {
        await api.post('/customers', payload);
        toast({
          title: 'Success',
          description: 'Customer created successfully',
        });
      }

      onSuccess();
    } catch (error: any) {
      toast({
        title: 'Error',
        description: error.response?.data?.detail || 'Failed to save customer',
        variant: 'destructive',
      });
    } finally {
      setLoading(false);
    }
  };

  const handleInputChange = (field: string, value: string) => {
    setFormData(prev => ({ ...prev, [field]: value }));
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[600px] max-h-[80vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>
            {customer ? 'Edit Customer' : 'Create New Customer'}
          </DialogTitle>
          <DialogDescription>
            {customer 
              ? 'Update the customer information below.'
              : 'Fill in the customer information below.'
            }
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            {/* Name */}
            <div className="space-y-2">
              <Label htmlFor="name">Name *</Label>
              <Input
                id="name"
                value={formData.name}
                onChange={(e) => handleInputChange('name', e.target.value)}
                required
              />
            </div>

            {/* Email */}
            <div className="space-y-2">
              <Label htmlFor="email">Email</Label>
              <Input
                id="email"
                type="email"
                value={formData.email}
                onChange={(e) => handleInputChange('email', e.target.value)}
              />
            </div>

            {/* Company */}
            <div className="space-y-2">
              <Label htmlFor="company">Company</Label>
              <Input
                id="company"
                value={formData.company}
                onChange={(e) => handleInputChange('company', e.target.value)}
              />
            </div>

            {/* Phone */}
            <div className="space-y-2">
              <Label htmlFor="phone">Phone</Label>
              <Input
                id="phone"
                value={formData.phone}
                onChange={(e) => handleInputChange('phone', e.target.value)}
              />
            </div>

            {/* T-Shirt Size */}
            <div className="space-y-2">
              <Label htmlFor="t_shirt_size">T-Shirt Size</Label>
              <Select
                value={formData.t_shirt_size}
                onValueChange={(value) => handleInputChange('t_shirt_size', value)}
              >
                <SelectTrigger>
                  <SelectValue placeholder="Select size" />
                </SelectTrigger>
                <SelectContent>
                  {T_SHIRT_SIZES.map((size) => (
                    <SelectItem key={size} value={size}>
                      {size}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {/* Segment */}
            <div className="space-y-2">
              <Label htmlFor="segment">Segment</Label>
              <Select
                value={formData.segment}
                onValueChange={(value) => handleInputChange('segment', value)}
              >
                <SelectTrigger>
                  <SelectValue placeholder="Select segment" />
                </SelectTrigger>
                <SelectContent>
                  {SEGMENTS.map((segment) => (
                    <SelectItem key={segment} value={segment}>
                      {segment}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {/* Vertical */}
            <div className="space-y-2">
              <Label htmlFor="vertical">Vertical</Label>
              <Select
                value={formData.vertical}
                onValueChange={(value) => handleInputChange('vertical', value)}
              >
                <SelectTrigger>
                  <SelectValue placeholder="Select vertical" />
                </SelectTrigger>
                <SelectContent>
                  {VERTICALS.map((vertical) => (
                    <SelectItem key={vertical} value={vertical}>
                      {vertical}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {/* Strategic Importance */}
            <div className="space-y-2">
              <Label htmlFor="strategic_importance">Strategic Importance</Label>
              <Select
                value={formData.strategic_importance}
                onValueChange={(value) => handleInputChange('strategic_importance', value)}
              >
                <SelectTrigger>
                  <SelectValue placeholder="Select importance" />
                </SelectTrigger>
                <SelectContent>
                  {IMPORTANCE_LEVELS.map((level) => (
                    <SelectItem key={level} value={level}>
                      {level}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {/* ARR */}
            <div className="space-y-2">
              <Label htmlFor="arr">Annual Recurring Revenue</Label>
              <Input
                id="arr"
                type="number"
                step="0.01"
                value={formData.arr}
                onChange={(e) => handleInputChange('arr', e.target.value)}
                placeholder="0.00"
              />
            </div>

            {/* Employee Count */}
            <div className="space-y-2">
              <Label htmlFor="employee_count">Employee Count</Label>
              <Input
                id="employee_count"
                type="number"
                value={formData.employee_count}
                onChange={(e) => handleInputChange('employee_count', e.target.value)}
                placeholder="0"
              />
            </div>

            {/* Geographic Region */}
            <div className="space-y-2 col-span-2">
              <Label htmlFor="geographic_region">Geographic Region</Label>
              <Input
                id="geographic_region"
                value={formData.geographic_region}
                onChange={(e) => handleInputChange('geographic_region', e.target.value)}
                placeholder="e.g., North America, Europe, Asia"
              />
            </div>
          </div>

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={loading}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={loading}>
              {loading ? 'Saving...' : customer ? 'Update' : 'Create'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
