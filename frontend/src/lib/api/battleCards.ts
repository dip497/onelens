import axios from 'axios';
import { BattleCard, BattleCardStatus, BattleCardSectionType, ScrapingJob } from '@/types/product';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1';

interface BattleCardFilters {
  product_id?: string;
  competitor_id?: string;
  status?: BattleCardStatus;
}

interface BattleCardCreate {
  product_id: string;
  competitor_id: string;
  sections: Array<{
    section_type: BattleCardSectionType;
    content: any;
    order_index: number;
  }>;
}

interface BattleCardUpdate {
  status?: BattleCardStatus;
  sections?: Array<{
    section_type?: BattleCardSectionType;
    content?: any;
    order_index?: number;
  }>;
}

interface BattleCardGenerateRequest {
  competitor_id: string;
  include_sections?: BattleCardSectionType[];
}

interface CompetitorScrapingRequest {
  job_type: string;
  target_urls?: string[];
}

export const battleCardsApi = {
  // Battle Card CRUD
  getBattleCards: async (filters?: BattleCardFilters): Promise<BattleCard[]> => {
    const params = new URLSearchParams();
    if (filters?.product_id) params.append('product_id', filters.product_id);
    if (filters?.competitor_id) params.append('competitor_id', filters.competitor_id);
    if (filters?.status) params.append('status', filters.status);
    
    const response = await axios.get(`${API_BASE_URL}/battle-cards?${params.toString()}`);
    return response.data;
  },

  getBattleCard: async (id: string): Promise<BattleCard> => {
    const response = await axios.get(`${API_BASE_URL}/battle-cards/${id}`);
    return response.data;
  },

  createBattleCard: async (data: BattleCardCreate): Promise<BattleCard> => {
    const response = await axios.post(`${API_BASE_URL}/battle-cards`, data);
    return response.data;
  },

  updateBattleCard: async (id: string, data: BattleCardUpdate): Promise<BattleCard> => {
    const response = await axios.put(`${API_BASE_URL}/battle-cards/${id}`, data);
    return response.data;
  },

  deleteBattleCard: async (id: string): Promise<void> => {
    await axios.delete(`${API_BASE_URL}/battle-cards/${id}`);
  },

  publishBattleCard: async (id: string): Promise<BattleCard> => {
    const response = await axios.post(`${API_BASE_URL}/battle-cards/${id}/publish`);
    return response.data;
  },

  archiveBattleCard: async (id: string): Promise<BattleCard> => {
    const response = await axios.post(`${API_BASE_URL}/battle-cards/${id}/archive`);
    return response.data;
  },

  // Battle Card Generation
  generateBattleCard: async (
    productId: string,
    data: BattleCardGenerateRequest
  ): Promise<BattleCard> => {
    const response = await axios.post(
      `${API_BASE_URL}/battle-cards/products/${productId}/generate`,
      data
    );
    return response.data;
  },

  // Competitor Scraping
  triggerCompetitorScraping: async (
    competitorId: string,
    data: CompetitorScrapingRequest
  ): Promise<ScrapingJob> => {
    const response = await axios.post(
      `${API_BASE_URL}/battle-cards/competitors/${competitorId}/scrape`,
      data
    );
    return response.data;
  },

  getCompetitorScrapingJobs: async (
    competitorId: string,
    status?: string
  ): Promise<ScrapingJob[]> => {
    const params = status ? `?status=${status}` : '';
    const response = await axios.get(
      `${API_BASE_URL}/battle-cards/competitors/${competitorId}/scraping-jobs${params}`
    );
    return response.data;
  },
};