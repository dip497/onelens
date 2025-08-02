import React from 'react';
import { useNavigate } from 'react-router-dom';
import { MoreHorizontal, Users, Layers, ExternalLink } from 'lucide-react';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  DropdownMenuSeparator,
} from '@/components/ui/dropdown-menu';
import { Badge } from '@/components/ui/badge';
import { Product } from '@/types/product';

interface ProductListProps {
  products: Product[];
}

export function ProductList({ products }: ProductListProps) {
  const navigate = useNavigate();

  const handleProductClick = (productId: string) => {
    navigate(`/personas/${productId}`);
  };

  const handleEditProduct = (productId: string) => {
    navigate(`/personas/${productId}/edit`);
  };

  const handleViewBattleCards = (productId: string) => {
    navigate(`/personas/${productId}/battle-cards`);
  };

  if (products.length === 0) {
    return (
      <Card>
        <CardContent className="flex flex-col items-center justify-center py-12">
          <p className="text-muted-foreground mb-4">No products found</p>
          <p className="text-sm text-muted-foreground">
            Create your first product to get started
          </p>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
      {products.map((product) => (
        <Card
          key={product.id}
          className="hover:shadow-lg transition-shadow cursor-pointer"
          onClick={() => handleProductClick(product.id)}
        >
          <CardHeader className="flex flex-row items-start justify-between space-y-0">
            <div className="space-y-1">
              <CardTitle className="text-lg">{product.name}</CardTitle>
              {product.tagline && (
                <CardDescription className="text-sm">
                  {product.tagline}
                </CardDescription>
              )}
            </div>
            <DropdownMenu>
              <DropdownMenuTrigger asChild onClick={(e) => e.stopPropagation()}>
                <Button variant="ghost" size="icon">
                  <MoreHorizontal className="h-4 w-4" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem onClick={(e) => {
                  e.stopPropagation();
                  handleEditProduct(product.id);
                }}>
                  Edit Product
                </DropdownMenuItem>
                <DropdownMenuItem onClick={(e) => {
                  e.stopPropagation();
                  handleViewBattleCards(product.id);
                }}>
                  View Battle Cards
                </DropdownMenuItem>
                {product.website && (
                  <>
                    <DropdownMenuSeparator />
                    <DropdownMenuItem onClick={(e) => {
                      e.stopPropagation();
                      window.open(product.website, '_blank');
                    }}>
                      <ExternalLink className="mr-2 h-4 w-4" />
                      Visit Website
                    </DropdownMenuItem>
                  </>
                )}
              </DropdownMenuContent>
            </DropdownMenu>
          </CardHeader>
          <CardContent>
            {product.description && (
              <p className="text-sm text-muted-foreground line-clamp-2 mb-4">
                {product.description}
              </p>
            )}
            <div className="flex items-center gap-4 text-sm text-muted-foreground">
              <div className="flex items-center gap-1">
                <Users className="h-3 w-3" />
                <span>{product.segments?.length || 0} segments</span>
              </div>
              <div className="flex items-center gap-1">
                <Layers className="h-3 w-3" />
                <span>{product.modules?.length || 0} modules</span>
              </div>
            </div>
            {product.modules && product.modules.length > 0 && (
              <div className="flex flex-wrap gap-1 mt-3">
                {product.modules.slice(0, 3).map((module) => (
                  <Badge key={module.id} variant="secondary" className="text-xs">
                    {module.name}
                  </Badge>
                ))}
                {product.modules.length > 3 && (
                  <Badge variant="outline" className="text-xs">
                    +{product.modules.length - 3} more
                  </Badge>
                )}
              </div>
            )}
          </CardContent>
        </Card>
      ))}
    </div>
  );
}