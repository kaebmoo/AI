import axios from 'axios';

// Use same base URL as other services or from environment
const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1';

const getAuthHeader = () => {
    const token = localStorage.getItem('token');
    return { Authorization: `Bearer ${token}` };
};

export interface AIProvider {
    id: string;
    name: string;
    display_name: string;
    model: string;
    icon: string;
    is_default: boolean;
}

export interface AIConfig {
    default_provider: string;
    claude_enabled: boolean;
    gemini_enabled: boolean;
    matcha_enabled: boolean;
    claude_model: string;
    gemini_model: string;
    matcha_model: string;
    matcha_api_url: string;
    claude_extended_thinking: boolean;
    claude_thinking_budget_tokens: number;
}

export interface FeatureFlags {
    rag_enabled: boolean;
    auto_context_detection: boolean;
    debug_mode: boolean;
    log_queries: boolean;
    collect_feedback: boolean;
    two_pass_enabled: boolean;
    value_lookup_enabled: boolean;
}

export const adminService = {
    refreshCache: async () => {
        const response = await axios.post(`${API_URL}/admin/refresh-cache`, {}, {
            headers: getAuthHeader()
        });
        return response.data;
    },

    getStats: async () => {
        const response = await axios.get(`${API_URL}/admin/stats`, {
            headers: getAuthHeader()
        });
        return response.data;
    },

    // AI Configuration Management
    getAIConfig: async () => {
        const response = await axios.get(`${API_URL}/admin/config/ai`, {
            headers: getAuthHeader()
        });
        return response.data;
    },

    updateAIConfig: async (config: Partial<AIConfig>) => {
        const response = await axios.put(`${API_URL}/admin/config/ai`, config, {
            headers: getAuthHeader()
        });
        return response.data;
    },

    getProviders: async (): Promise<AIProvider[]> => {
        const response = await axios.get(`${API_URL}/admin/config/ai/providers`, {
            headers: getAuthHeader()
        });
        return response.data;
    },

    getAvailableModels: async (provider: string): Promise<string[]> => {
        const response = await axios.get(`${API_URL}/admin/config/ai/models/${provider}`, {
            headers: getAuthHeader()
        });
        return response.data;
    },

    // Feature Flags Management
    getFeatureFlags: async (): Promise<FeatureFlags> => {
        const response = await axios.get(`${API_URL}/admin/config/features`, {
            headers: getAuthHeader()
        });
        return response.data;
    },

    toggleFeature: async (featureName: string, enabled: boolean) => {
        const response = await axios.post(
            `${API_URL}/admin/config/features/${featureName}/toggle?enabled=${enabled}`,
            {},
            { headers: getAuthHeader() }
        );
        return response.data;
    },

    clearConfigCache: async () => {
        const response = await axios.post(`${API_URL}/admin/config/cache/clear`, {}, {
            headers: getAuthHeader()
        });
        return response.data;
    },

    rebuildKeywordIndex: async () => {
        const response = await axios.post(`${API_URL}/admin/config/rebuild-keyword-index`, {}, {
            headers: getAuthHeader()
        });
        return response.data;
    },

    syncBrain: async () => {
        const response = await axios.post(`${API_URL}/admin/sync-brain`, {}, {
            headers: getAuthHeader()
        });
        return response.data;
    }
};
