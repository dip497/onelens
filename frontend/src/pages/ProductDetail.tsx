import React, { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
  ArrowLeft,
  Edit,
  MoreHorizontal,
  Plus,
  Users,
  Layers,
  Shield,
  ExternalLink,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from '@/components/ui/tabs';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { productsApi } from '@/lib/api/products';
import { SegmentManager } from '@/components/personas/SegmentManager';
import { ModuleManager } from '@/components/personas/ModuleManager';
import { CompetitorComparison } from '@/components/personas/CompetitorComparison';
import { BattleCardList } from '@/components/personas/BattleCardList';
import { FeatureAssignment } from '@/components/personas/FeatureAssignment';
import { ModuleFeatureManager } from '@/components/personas/ModuleFeatureManager';

export function ProductDetail() {
  const { productId } = useParams<{ productId: string }>();
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState('overview');

  const { data: product, isLoading, error } = useQuery({
    queryKey: ['product', productId],
    queryFn: () => productsApi.getProduct(productId!),
    enabled: !!productId,
  });

  if (isLoading) {
    return (
      <div className="space-y-6">
        <div className="flex items-center gap-4">
          <Skeleton className="h-10 w-10" />
          <div className="space-y-2">
            <Skeleton className="h-8 w-64" />
            <Skeleton className="h-4 w-96" />
          </div>
        </div>
        <Skeleton className="h-96 w-full" />
      </div>
    );
  }

  if (error || !product) {
    return (
      <div className="flex items-center justify-center h-96">
        <Card className="w-96">
          <CardHeader>
            <CardTitle className="text-destructive">Error Loading Product</CardTitle>
            <CardDescription>
              Unable to load product details. Please try again.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Button onClick={() => navigate('/personas')}>
              Back to Products
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div className="flex items-start gap-4">
          <Button
            variant="ghost"
            size="icon"
            onClick={() => navigate('/personas')}
          >
            <ArrowLeft className="h-4 w-4" />
          </Button>
          <div>
            <h1 className="text-3xl font-bold tracking-tight">{product.name}</h1>
            {product.tagline && (
              <p className="text-muted-foreground mt-1">{product.tagline}</p>
            )}
            <div className="flex items-center gap-4 mt-4">
              {product.website && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => window.open(product.website, '_blank')}
                >
                  <ExternalLink className="mr-2 h-4 w-4" />
                  Visit Website
                </Button>
              )}
              <Badge variant="secondary">
                {product.segments?.length || 0} Segments
              </Badge>
              <Badge variant="secondary">
                {product.modules?.length || 0} Modules
              </Badge>
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            onClick={() => navigate(`/personas/${productId}/edit`)}
          >
            <Edit className="mr-2 h-4 w-4" />
            Edit
          </Button>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="icon">
                <MoreHorizontal className="h-4 w-4" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem
                onClick={() => navigate(`/personas/${productId}/battle-cards/new`)}
              >
                Generate Battle Card
              </DropdownMenuItem>
              <DropdownMenuItem className="text-destructive">
                Delete Product
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>

      {/* Content Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList>
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="segments">
            <Users className="mr-2 h-4 w-4" />
            Segments
          </TabsTrigger>
          <TabsTrigger value="modules">
            <Layers className="mr-2 h-4 w-4" />
            Modules
          </TabsTrigger>
          <TabsTrigger value="module-features">Module Features</TabsTrigger>
          <TabsTrigger value="epic-features">Epic Features</TabsTrigger>
          <TabsTrigger value="competitors">
            <Shield className="mr-2 h-4 w-4" />
            Competitors
          </TabsTrigger>
          <TabsTrigger value="battle-cards">Battle Cards</TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>Product Overview</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              {product.description && (
                <div>
                  <h3 className="font-medium mb-2">Description</h3>
                  <p className="text-muted-foreground">{product.description}</p>
                </div>
              )}
              <div className="grid gap-4 md:grid-cols-2">
                <div>
                  <h3 className="font-medium mb-2">Created</h3>
                  <p className="text-muted-foreground">
                    {new Date(product.created_at).toLocaleDateString()}
                  </p>
                </div>
                <div>
                  <h3 className="font-medium mb-2">Last Updated</h3>
                  <p className="text-muted-foreground">
                    {new Date(product.updated_at).toLocaleDateString()}
                  </p>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Quick Stats */}
          <div className="grid gap-4 md:grid-cols-3">
            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">
                  Total Features
                </CardTitle>
                <Layers className="h-4 w-4 text-muted-foreground" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">
                  {product.modules?.reduce(
                    (acc, m) => acc + (m.feature_count || 0),
                    0
                  ) || 0}
                </div>
              </CardContent>
            </Card>
            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">
                  Target Segments
                </CardTitle>
                <Users className="h-4 w-4 text-muted-foreground" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">
                  {product.segments?.length || 0}
                </div>
              </CardContent>
            </Card>
            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">
                  Battle Cards
                </CardTitle>
                <Shield className="h-4 w-4 text-muted-foreground" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">0</div>
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="segments">
          <SegmentManager productId={productId!} />
        </TabsContent>

        <TabsContent value="modules">
          <ModuleManager productId={productId!} />
        </TabsContent>

        <TabsContent value="module-features">
          <div className="space-y-6">
            {product.modules && product.modules.length > 0 ? (
              product.modules.map((module) => (
                <div key={module.id}>
                  <ModuleFeatureManager
                    moduleId={module.id}
                    moduleName={module.name}
                  />
                </div>
              ))
            ) : (
              <Card>
                <CardContent className="py-12 text-center">
                  <p className="text-muted-foreground">
                    Please create modules first before adding module features
                  </p>
                  <Button
                    className="mt-4"
                    onClick={() => setActiveTab('modules')}
                  >
                    Go to Modules
                  </Button>
                </CardContent>
              </Card>
            )}
          </div>
        </TabsContent>

        <TabsContent value="epic-features">
          <FeatureAssignment productId={productId!} />
        </TabsContent>

        <TabsContent value="competitors">
          <CompetitorComparison productId={productId!} />
        </TabsContent>

        <TabsContent value="battle-cards">
          <BattleCardList productId={productId!} />
        </TabsContent>
      </Tabs>
    </div>
  );
}