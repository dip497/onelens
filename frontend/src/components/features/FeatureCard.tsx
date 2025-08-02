import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Progress } from '@/components/ui/progress';
import { 
  TrendingUp, Target, Users, Eye, BarChart3, 
  AlertCircle, ChevronRight, Hash
} from 'lucide-react';
import { Feature, PriorityScore } from '@/types';
import { useNavigate } from 'react-router-dom';

interface FeatureCardProps {
  feature: Feature & {
    priority_score?: PriorityScore;
    rfp_occurrence_count?: number;
    tags?: string[];
  };
}

export function FeatureCard({ feature }: FeatureCardProps) {
  const navigate = useNavigate();
  
  const getPriorityColor = (score?: number) => {
    if (!score) return 'text-gray-500 bg-gray-50 border-gray-200';
    if (score >= 70) return 'text-green-600 bg-green-50 border-green-200';
    if (score >= 40) return 'text-yellow-600 bg-yellow-50 border-yellow-200';
    return 'text-red-600 bg-red-50 border-red-200';
  };

  const getPriorityLabel = (score?: number) => {
    if (!score) return 'No Score';
    if (score >= 70) return 'High';
    if (score >= 40) return 'Medium';
    return 'Low';
  };

  const handleViewAnalysis = () => {
    navigate(`/features/${feature.id}/analysis`);
  };

  return (
    <Card className="hover:shadow-md transition-shadow duration-200">
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between">
          <div className="space-y-1 flex-1">
            <CardTitle className="text-lg leading-tight">{feature.title}</CardTitle>
            <CardDescription className="text-sm line-clamp-2">
              {feature.description || 'No description available'}
            </CardDescription>
          </div>
          <div className={`ml-4 px-3 py-2 rounded-lg border ${getPriorityColor(feature.priority_score?.final_score)}`}>
            <div className="text-xl font-bold text-center">
              {feature.priority_score?.final_score?.toFixed(0) || 'N/A'}
            </div>
            <div className="text-xs font-medium text-center">
              {getPriorityLabel(feature.priority_score?.final_score)}
            </div>
          </div>
        </div>
      </CardHeader>
      
      <CardContent className="space-y-4">
        {/* Tags Section */}
        <div className="flex flex-wrap gap-2">
          <Badge variant="secondary" className="text-xs">
            <Hash className="w-3 h-3 mr-1" />
            Not AI Enabled
          </Badge>
          {feature.tags?.map((tag, index) => (
            <Badge key={index} variant="outline" className="text-xs">
              {tag}
            </Badge>
          ))}
        </div>

        {/* Metrics Section */}
        <div className="grid grid-cols-2 gap-4">
          <div className="flex items-center space-x-2">
            <Users className="w-4 h-4 text-blue-500" />
            <div>
              <div className="text-sm font-medium">{feature.customer_request_count}</div>
              <div className="text-xs text-muted-foreground">Customer Requests</div>
            </div>
          </div>
          
          <div className="flex items-center space-x-2">
            <BarChart3 className="w-4 h-4 text-purple-500" />
            <div>
              <div className="text-sm font-medium">{feature.rfp_occurrence_count || 0}</div>
              <div className="text-xs text-muted-foreground">RFP Occurrences</div>
            </div>
          </div>
        </div>

        {/* Priority Score Breakdown */}
        {feature.priority_score && (
          <div className="space-y-2">
            <div className="text-xs font-medium text-muted-foreground">Priority Breakdown</div>
            <div className="space-y-1">
              <div className="flex justify-between text-xs">
                <span>Customer Impact</span>
                <span>{feature.priority_score.customer_impact_score?.toFixed(1) || 'N/A'}</span>
              </div>
              <Progress 
                value={feature.priority_score.customer_impact_score || 0} 
                className="h-1"
              />
            </div>
          </div>
        )}

        {/* Action Button */}
        <Button 
          onClick={handleViewAnalysis}
          className="w-full"
          variant="outline"
        >
          <Eye className="w-4 h-4 mr-2" />
          View Full Analysis
          <ChevronRight className="w-4 h-4 ml-2" />
        </Button>
      </CardContent>
    </Card>
  );
}
