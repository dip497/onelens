import axios, { AxiosError } from 'axios';
import type { 
  Epic, 
  Feature, 
  PaginatedResponse, 
  EpicCreateInput, 
  FeatureCreateInput,
  EpicSummary,
  FeatureRanking,
  ApiError
} from '@/types';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';
const API_PREFIX = '/api/v1';

// Create axios instance with default config
const api = axios.create({
  baseURL: `${API_BASE_URL}${API_PREFIX}`,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Add auth token to requests
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('auth_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Handle errors
api.interceptors.response.use(
  (response) => response,
  (error: AxiosError<ApiError>) => {
    if (error.response?.status === 401) {
      // Handle unauthorized
      localStorage.removeItem('auth_token');
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);

// Epic API
export const epicApi = {
  // List epics with pagination and filters
  list: async (params?: {
    page?: number;
    size?: number;
    status?: string;
    search?: string;
    created_by?: string;
    assigned_to?: string;
  }): Promise<PaginatedResponse<Epic>> => {
    const response = await api.get('/epics', { params });
    return response.data;
  },

  // Get single epic
  get: async (id: string): Promise<Epic> => {
    const response = await api.get(`/epics/${id}`);
    return response.data;
  },

  // Create epic
  create: async (data: EpicCreateInput): Promise<Epic> => {
    const response = await api.post('/epics', data);
    return response.data;
  },

  // Update epic
  update: async (id: string, data: Partial<EpicCreateInput>): Promise<Epic> => {
    const response = await api.put(`/epics/${id}`, data);
    return response.data;
  },

  // Delete epic
  delete: async (id: string): Promise<void> => {
    await api.delete(`/epics/${id}`);
  },

  // Trigger analysis
  analyze: async (id: string): Promise<{ message: string; epic_id: string; status: string }> => {
    const response = await api.post(`/epics/${id}/analyze`);
    return response.data;
  },

  // Get summary by status
  getSummaryByStatus: async (): Promise<EpicSummary[]> => {
    const response = await api.get('/epics/summary/by-status');
    return response.data;
  },

  // Get analysis results
  getAnalysisResults: async (id: string): Promise<{
    epic_id: string;
    epic_title: string;
    epic_status: string;
    features_count: number;
    features: Array<{
      feature_id: string;
      title: string;
      description: string;
      priority_score: number;
      analyses: {
        report?: {
          // Core scores
          priority_score: number | null;
          business_impact_score: number | null;
          
          // Trend Analysis
          trend_alignment_status: boolean;
          trend_keywords: string[];
          trend_justification: string | null;
          
          // Business Impact
          revenue_potential: 'HIGH' | 'MEDIUM' | 'LOW' | null;
          user_adoption_forecast: 'HIGH' | 'MEDIUM' | 'LOW' | null;
          
          // Market Opportunity
          market_opportunity_score: number | null;
          total_competitors_analyzed: number | null;
          competitors_providing_count: number | null;
          
          // Geographic Insights
          geographic_insights: {
            top_markets: Array<{
              country: string;
              market_size: number;
              opportunity_rating: string;
              regulatory_factors: string[];
            }>;
            total_market_size: number;
            regulatory_considerations: string[];
          } | null;
          
          // Competitive Analysis
          competitor_pros_cons: {
            main_competitors: Array<{
              name: string;
              strengths: string[];
              weaknesses: string[];
            }>;
            market_gaps: string[];
            competitive_advantages: string[];
          } | null;
          competitive_positioning: string | null;
          
          // Metadata
          generated_by_workflow: string;
          created_at: string;
          updated_at: string;
        };
      };
    }>;
  }> => {
    const response = await api.get(`/epics/${id}/analysis/results`);
    return response.data;
  },
};

// Feature API
export const featureApi = {
  // List features
  list: async (params?: {
    page?: number;
    size?: number;
    epic_id?: string;
    search?: string;
    has_priority_score?: boolean;
    min_request_count?: number;
  }): Promise<PaginatedResponse<Feature>> => {
    const response = await api.get('/features', { params });
    return response.data;
  },

  // Get single feature
  get: async (id: string, include_analysis = false): Promise<Feature> => {
    const response = await api.get(`/features/${id}`, {
      params: { include_analysis }
    });
    return response.data;
  },

  // Create feature
  create: async (data: FeatureCreateInput): Promise<Feature> => {
    const response = await api.post('/features', data);
    return response.data;
  },

  // Update feature
  update: async (id: string, data: Partial<FeatureCreateInput>): Promise<Feature> => {
    const response = await api.put(`/features/${id}`, data);
    return response.data;
  },

  // Delete feature
  delete: async (id: string): Promise<void> => {
    await api.delete(`/features/${id}`);
  },

  // Trigger analysis
  analyze: async (id: string, analysis_types?: string[]): Promise<{ 
    message: string; 
    feature_id: string; 
    analysis_types: string[];
    status: string;
  }> => {
    const response = await api.post(`/features/${id}/analyze`, { analysis_types });
    return response.data;
  },

  // Search similar features
  searchSimilar: async (text: string, threshold = 0.7, limit = 10): Promise<Feature[]> => {
    const response = await api.post('/features/search/similar', null, {
      params: { text, threshold, limit }
    });
    return response.data;
  },
};

// Analysis API
export const analysisApi = {
  // Get feature rankings
  getFeatureRankings: async (epic_id?: string, limit = 10): Promise<FeatureRanking[]> => {
    const response = await api.get('/analysis/rankings', {
      params: { epic_id, limit }
    });
    return response.data;
  },

  // Recalculate priority scores
  recalculatePriorityScores: async (epic_id?: string): Promise<{ 
    message: string; 
    updated_count: number;
  }> => {
    const response = await api.post('/analysis/recalculate-scores', { epic_id });
    return response.data;
  },
};

// Export the api instance for custom requests
export default api;