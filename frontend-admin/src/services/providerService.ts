import axios from 'axios';
import { API_URL } from './api';

const getAuthHeader = () => {
    const token = localStorage.getItem('token');
    return { Authorization: `Bearer ${token}` };
};

// Type definitions
export interface AIProviderDetailed {
    id: string;
    name: string;
    display_name?: string;
    icon?: string;
    is_active: boolean;
    is_default: boolean;
    api_key_env_var?: string;
    api_url_env_var?: string;
    default_api_url?: string;
    description?: string;
    priority: number;
    created_at?: string;
    updated_at?: string;
}

export interface AIModel {
    id: number;
    provider_id: string;
    model_id: string;
    display_name?: string;
    is_active: boolean;
    is_default: boolean;
    context_window?: number;
    supports_vision: boolean;
    cost_per_1m_tokens?: number;
    description?: string;
    priority: number;
    tier?: string;
    created_at?: string;
    updated_at?: string;
}

export interface CreateProviderRequest {
    provider_id: string;
    name: string;
    display_name?: string;
    icon?: string;
    is_active?: boolean;
    is_default?: boolean;
    api_key_env_var?: string;
    api_url_env_var?: string;
    default_api_url?: string;
    description?: string;
    priority?: number;
}

export interface UpdateProviderRequest {
    name?: string;
    display_name?: string;
    icon?: string;
    is_active?: boolean;
    is_default?: boolean;
    api_key_env_var?: string;
    api_url_env_var?: string;
    default_api_url?: string;
    description?: string;
    priority?: number;
}

export interface CreateModelRequest {
    model_id: string;
    display_name?: string;
    is_active?: boolean;
    is_default?: boolean;
    context_window?: number;
    supports_vision?: boolean;
    cost_per_1m_tokens?: number;
    description?: string;
    priority?: number;
}

export interface UpdateModelRequest {
    display_name?: string;
    is_active?: boolean;
    is_default?: boolean;
    context_window?: number;
    supports_vision?: boolean;
    cost_per_1m_tokens?: number;
    description?: string;
    priority?: number;
}

export const providerService = {
    // Provider CRUD operations
    getAllProviders: async (includeInactive: boolean = false): Promise<AIProviderDetailed[]> => {
        const response = await axios.get(`${API_URL}/admin/providers`, {
            headers: getAuthHeader(),
            params: { include_inactive: includeInactive }
        });
        return response.data;
    },

    createProvider: async (data: CreateProviderRequest): Promise<AIProviderDetailed> => {
        const response = await axios.post(`${API_URL}/admin/providers`, data, {
            headers: getAuthHeader()
        });
        return response.data;
    },

    updateProvider: async (providerId: string, data: UpdateProviderRequest): Promise<AIProviderDetailed> => {
        const response = await axios.put(`${API_URL}/admin/providers/${providerId}`, data, {
            headers: getAuthHeader()
        });
        return response.data;
    },

    deleteProvider: async (providerId: string): Promise<void> => {
        await axios.delete(`${API_URL}/admin/providers/${providerId}`, {
            headers: getAuthHeader()
        });
    },

    // Model CRUD operations
    getModelsByProvider: async (providerId: string, includeInactive: boolean = false): Promise<AIModel[]> => {
        const response = await axios.get(`${API_URL}/admin/providers/${providerId}/models`, {
            headers: getAuthHeader(),
            params: { include_inactive: includeInactive }
        });
        return response.data;
    },

    createModel: async (providerId: string, data: CreateModelRequest): Promise<AIModel> => {
        const response = await axios.post(`${API_URL}/admin/providers/${providerId}/models`, data, {
            headers: getAuthHeader()
        });
        return response.data;
    },

    updateModel: async (modelId: number, data: UpdateModelRequest): Promise<AIModel> => {
        const response = await axios.put(`${API_URL}/admin/models/${modelId}`, data, {
            headers: getAuthHeader()
        });
        return response.data;
    },

    deleteModel: async (modelId: number): Promise<void> => {
        await axios.delete(`${API_URL}/admin/models/${modelId}`, {
            headers: getAuthHeader()
        });
    }
};
