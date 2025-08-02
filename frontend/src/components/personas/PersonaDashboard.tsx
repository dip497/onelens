import React, { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Package, Users, Layers, Shield, AlertCircle, Settings } from 'lucide-react';
import { useQuery } from '@tanstack/react-query';
import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Skeleton } from '@/components/ui/skeleton';
import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1';

interface PersonaStats {
  initialized: boolean;
  product_name?: string;
  product_id?: string;
  total_modules: number;
  total_features: number;
  total_segments: number;
  total_competitors: number;
  total_battle_cards: number;
}

export function PersonaDashboard() {
  const navigate = useNavigate();

  const { data: stats, isLoading, error } = useQuery({
    queryKey: ['persona-stats'],
    queryFn: async () => {
      const response = await axios.get<PersonaStats>(`${API_BASE_URL}/persona/stats`);
      return response.data;
    },
  });

  // If persona is initialized, redirect to the detail page
  useEffect(() => {
    if (stats?.initialized && stats.product_id) {
      navigate(`/personas/${stats.product_id}`);
    }
  }, [stats, navigate]);

  if (error) {
    return (
      <div className="flex items-center justify-center h-96">
        <Alert variant="destructive" className="max-w-md">
          <AlertCircle className="h-4 w-4" />
          <AlertTitle>Error Loading Persona</AlertTitle>
          <AlertDescription>
            There was an error loading the persona data. Please try again.
          </AlertDescription>
        </Alert>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-8 w-64" />
        <div className="grid gap-4 md:grid-cols-3">
          <Skeleton className="h-32" />
          <Skeleton className="h-32" />
          <Skeleton className="h-32" />
        </div>
      </div>
    );
  }

  if (!stats?.initialized) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Product Persona</h1>
          <p className="text-muted-foreground">
            Define your product and compete intelligently
          </p>
        </div>

        <Alert>
          <Package className="h-4 w-4" />
          <AlertTitle>Persona Not Initialized</AlertTitle>
          <AlertDescription>
            Your company persona has not been set up yet. Please run the initialization
            script to create your product persona.
          </AlertDescription>
        </Alert>

        <Card>
          <CardHeader>
            <CardTitle>What is a Product Persona?</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <p className="text-muted-foreground">
              Your product persona represents your company's product in the competitive
              intelligence system. It includes:
            </p>
            <ul className="list-disc list-inside space-y-2 text-muted-foreground">
              <li>Product information (name, description, website)</li>
              <li>Modules that organize your features</li>
              <li>Customer segments you target</li>
              <li>Competitive comparisons and battle cards</li>
            </ul>
            <div className="pt-4">
              <p className="text-sm text-muted-foreground mb-2">
                To initialize your persona, run the following command in the backend:
              </p>
              <code className="block p-3 bg-muted rounded text-sm">
                python ensure_single_persona.py
              </code>
            </div>
          </CardContent>
        </Card>
      </div>
    );
  }

  // This will rarely be shown as we redirect above
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">{stats.product_name}</h1>
          <p className="text-muted-foreground">
            Your product persona and competitive intelligence
          </p>
        </div>
        <Button onClick={() => navigate(`/personas/${stats.product_id}`)}>
          <Settings className="mr-2 h-4 w-4" />
          Manage Persona
        </Button>
      </div>

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Modules</CardTitle>
            <Layers className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{stats.total_modules}</div>
            <p className="text-xs text-muted-foreground">Product modules</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Features</CardTitle>
            <Package className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{stats.total_features}</div>
            <p className="text-xs text-muted-foreground">Total features</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Competitors</CardTitle>
            <Users className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{stats.total_competitors}</div>
            <p className="text-xs text-muted-foreground">Tracked competitors</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Battle Cards</CardTitle>
            <Shield className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{stats.total_battle_cards}</div>
            <p className="text-xs text-muted-foreground">Sales enablement</p>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}