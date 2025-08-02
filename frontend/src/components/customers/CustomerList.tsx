import React, { useState, useEffect } from 'react';
import { Plus, Search, Edit, Trash2, User, Building, Mail, Phone, Shirt } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { useToast } from '@/components/ui/use-toast';
import api from '@/services/api';
import CustomerDialog from './CustomerDialog';

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

interface CustomerListResponse {
  items: Customer[];
  total: number;
  skip: number;
  limit: number;
}

export default function CustomerList() {
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingCustomer, setEditingCustomer] = useState<Customer | null>(null);
  const [totalCustomers, setTotalCustomers] = useState(0);
  const { toast } = useToast();

  const fetchCustomers = async () => {
    try {
      setLoading(true);
      const params = new URLSearchParams();
      if (searchQuery) {
        params.append('search', searchQuery);
      }
      
      const response = await api.get<CustomerListResponse>(`/customers?${params.toString()}`);
      setCustomers(response.data.items);
      setTotalCustomers(response.data.total);
    } catch (error) {
      toast({
        title: 'Error',
        description: 'Failed to fetch customers',
        variant: 'destructive',
      });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchCustomers();
  }, [searchQuery]);

  const handleCreateCustomer = () => {
    setEditingCustomer(null);
    setDialogOpen(true);
  };

  const handleEditCustomer = (customer: Customer) => {
    setEditingCustomer(customer);
    setDialogOpen(true);
  };

  const handleDeleteCustomer = async (customerId: string) => {
    if (!confirm('Are you sure you want to delete this customer?')) {
      return;
    }

    try {
      await api.delete(`/customers/${customerId}`);
      toast({
        title: 'Success',
        description: 'Customer deleted successfully',
      });
      fetchCustomers();
    } catch (error) {
      toast({
        title: 'Error',
        description: 'Failed to delete customer',
        variant: 'destructive',
      });
    }
  };

  const handleDialogSuccess = () => {
    setDialogOpen(false);
    setEditingCustomer(null);
    fetchCustomers();
  };

  const getSegmentColor = (segment?: string) => {
    switch (segment) {
      case 'Enterprise': return 'bg-purple-100 text-purple-800';
      case 'Large': return 'bg-blue-100 text-blue-800';
      case 'Medium': return 'bg-green-100 text-green-800';
      case 'Small': return 'bg-yellow-100 text-yellow-800';
      default: return 'bg-gray-100 text-gray-800';
    }
  };

  const getTShirtSizeColor = (size?: string) => {
    switch (size) {
      case 'XS': return 'bg-pink-100 text-pink-800';
      case 'S': return 'bg-blue-100 text-blue-800';
      case 'M': return 'bg-green-100 text-green-800';
      case 'L': return 'bg-yellow-100 text-yellow-800';
      case 'XL': return 'bg-orange-100 text-orange-800';
      case 'XXL': return 'bg-red-100 text-red-800';
      default: return 'bg-gray-100 text-gray-800';
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-3xl font-bold">Customer Management</h1>
          <p className="text-muted-foreground">
            Manage your customers and their information
          </p>
        </div>
        <Button onClick={handleCreateCustomer}>
          <Plus className="h-4 w-4 mr-2" />
          Add Customer
        </Button>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total Customers</CardTitle>
            <User className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{totalCustomers}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Enterprise</CardTitle>
            <Building className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {customers.filter(c => c.segment === 'Enterprise').length}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">With Email</CardTitle>
            <Mail className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {customers.filter(c => c.email).length}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">With T-Shirt Size</CardTitle>
            <Shirt className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {customers.filter(c => c.t_shirt_size).length}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Search and Filters */}
      <Card>
        <CardHeader>
          <CardTitle>Customers</CardTitle>
          <CardDescription>
            A list of all customers in your system
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex items-center space-x-2 mb-4">
            <div className="relative flex-1">
              <Search className="absolute left-2 top-2.5 h-4 w-4 text-muted-foreground" />
              <Input
                placeholder="Search customers..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="pl-8"
              />
            </div>
          </div>

          {/* Customer Table */}
          <div className="rounded-md border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Name</TableHead>
                  <TableHead>Company</TableHead>
                  <TableHead>Contact</TableHead>
                  <TableHead>T-Shirt Size</TableHead>
                  <TableHead>Segment</TableHead>
                  <TableHead>Vertical</TableHead>
                  <TableHead>Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {loading ? (
                  <TableRow>
                    <TableCell colSpan={7} className="text-center py-8">
                      Loading customers...
                    </TableCell>
                  </TableRow>
                ) : customers.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={7} className="text-center py-8">
                      No customers found
                    </TableCell>
                  </TableRow>
                ) : (
                  customers.map((customer) => (
                    <TableRow key={customer.id}>
                      <TableCell>
                        <div>
                          <div className="font-medium">{customer.name}</div>
                          {customer.email && (
                            <div className="text-sm text-muted-foreground flex items-center gap-1">
                              <Mail className="h-3 w-3" />
                              {customer.email}
                            </div>
                          )}
                        </div>
                      </TableCell>
                      <TableCell>
                        {customer.company && (
                          <div className="flex items-center gap-1">
                            <Building className="h-3 w-3 text-muted-foreground" />
                            {customer.company}
                          </div>
                        )}
                      </TableCell>
                      <TableCell>
                        {customer.phone && (
                          <div className="flex items-center gap-1">
                            <Phone className="h-3 w-3 text-muted-foreground" />
                            {customer.phone}
                          </div>
                        )}
                      </TableCell>
                      <TableCell>
                        {customer.t_shirt_size && (
                          <Badge className={getTShirtSizeColor(customer.t_shirt_size)}>
                            <Shirt className="h-3 w-3 mr-1" />
                            {customer.t_shirt_size}
                          </Badge>
                        )}
                      </TableCell>
                      <TableCell>
                        {customer.segment && (
                          <Badge className={getSegmentColor(customer.segment)}>
                            {customer.segment}
                          </Badge>
                        )}
                      </TableCell>
                      <TableCell>{customer.vertical}</TableCell>
                      <TableCell>
                        <div className="flex items-center gap-2">
                          <Button
                            variant="ghost"
                            size="icon"
                            onClick={() => handleEditCustomer(customer)}
                          >
                            <Edit className="h-4 w-4" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="icon"
                            onClick={() => handleDeleteCustomer(customer.id)}
                          >
                            <Trash2 className="h-4 w-4" />
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </div>
        </CardContent>
      </Card>

      {/* Customer Dialog */}
      <CustomerDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        customer={editingCustomer}
        onSuccess={handleDialogSuccess}
      />
    </div>
  );
}
