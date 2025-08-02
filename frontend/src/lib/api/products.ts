import axios from 'axios';
import { Product, ProductCreate, ProductUpdate } from '@/types/product';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1';

export const productsApi = {
  // Product CRUD
  getProducts: async (): Promise<Product[]> => {
    const response = await axios.get(`${API_BASE_URL}/products`);
    return response.data;
  },

  getProduct: async (id: string): Promise<Product> => {
    const response = await axios.get(`${API_BASE_URL}/products/${id}`);
    return response.data;
  },

  createProduct: async (data: ProductCreate): Promise<Product> => {
    const response = await axios.post(`${API_BASE_URL}/products`, data);
    return response.data;
  },

  updateProduct: async (id: string, data: ProductUpdate): Promise<Product> => {
    const response = await axios.put(`${API_BASE_URL}/products/${id}`, data);
    return response.data;
  },

  deleteProduct: async (id: string): Promise<void> => {
    await axios.delete(`${API_BASE_URL}/products/${id}`);
  },

  // Product Segments
  getProductSegments: async (productId: string) => {
    const response = await axios.get(`${API_BASE_URL}/products/${productId}/segments`);
    return response.data;
  },

  createProductSegment: async (productId: string, data: any) => {
    const response = await axios.post(`${API_BASE_URL}/products/${productId}/segments`, data);
    return response.data;
  },

  updateSegment: async (segmentId: string, data: any) => {
    const response = await axios.put(`${API_BASE_URL}/segments/${segmentId}`, data);
    return response.data;
  },

  deleteSegment: async (segmentId: string) => {
    await axios.delete(`${API_BASE_URL}/segments/${segmentId}`);
  },

  // Product Modules
  getProductModules: async (productId: string) => {
    const response = await axios.get(`${API_BASE_URL}/products/${productId}/modules`);
    return response.data;
  },

  createProductModule: async (productId: string, data: any) => {
    const response = await axios.post(`${API_BASE_URL}/products/${productId}/modules`, data);
    return response.data;
  },

  updateModule: async (moduleId: string, data: any) => {
    const response = await axios.put(`${API_BASE_URL}/modules/${moduleId}`, data);
    return response.data;
  },

  deleteModule: async (moduleId: string) => {
    await axios.delete(`${API_BASE_URL}/modules/${moduleId}`);
  },

  reorderModules: async (productId: string, moduleOrders: Array<{ id: string; order_index: number }>) => {
    const response = await axios.put(`${API_BASE_URL}/products/${productId}/modules/reorder`, {
      module_orders: moduleOrders,
    });
    return response.data;
  },

  updateModuleFeatures: async (moduleId: string, featureAssignments: any[]) => {
    const response = await axios.put(`${API_BASE_URL}/modules/${moduleId}/features`, {
      feature_assignments: featureAssignments,
    });
    return response.data;
  },
};