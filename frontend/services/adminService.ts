/**
 * NT AI Assistant - Admin Service
 * Frontend service for admin configuration management
 */

import api from './api';

// ============================================================
// Type Definitions
// ============================================================

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
}

export interface FeatureFlags {
    rag_enabled: boolean;
    auto_context_detection: boolean;
    debug_mode: boolean;
    log_queries: boolean;
    collect_feedback: boolean;
}

export interface AdminConfigResponse {
    ai: AIConfig;
    features: FeatureFlags;
    fallback_note: string;
}

export interface ContextItem {
    id: number;
    name: string;
    display_name: string;
    description?: string;
    main_view: string;
    keywords?: string;
    priority?: number;
    is_active?: boolean;
}

// ============================================================
// Admin Service
// ============================================================

export const adminService = {
    /**
     * Get complete AI configuration
     * Requires admin authentication
     */
    fetchAIConfig: async (): Promise<AdminConfigResponse> => {
        try {
            const response = await api.get<AdminConfigResponse>('/admin/config/ai');
            return response.data;
        } catch (error: any) {
            console.error('[AdminService] Failed to fetch AI config:', error);
            throw new Error(error.response?.data?.detail || 'Failed to fetch AI configuration');
        }
    },

    /**
     * Update AI configuration
     * Requires admin authentication
     */
    updateAIConfig: async (config: Partial<AIConfig>): Promise<{ status: string; message: string }> => {
        try {
            const response = await api.put('/admin/config/ai', config);
            return response.data;
        } catch (error: any) {
            console.error('[AdminService] Failed to update AI config:', error);
            throw new Error(error.response?.data?.detail || 'Failed to update AI configuration');
        }
    },

    /**
     * Get list of active AI providers
     * PUBLIC endpoint - can be called without admin auth
     */
    fetchProviders: async (): Promise<AIProvider[]> => {
        try {
            const response = await api.get<AIProvider[]>('/admin/config/ai/providers');
            return response.data;
        } catch (error: any) {
            console.error('[AdminService] Failed to fetch providers:', error);

            // Fallback to default provider if API fails
            return [
                {
                    id: 'matcha',
                    name: 'Matcha',
                    display_name: 'Matcha (NT Gateway)',
                    model: 'gpt-4.1',
                    icon: 'leaf',
                    is_default: true
                }
            ];
        }
    },

    /**
     * Get available models for a specific provider
     * Requires admin authentication
     */
    fetchAvailableModels: async (provider: string): Promise<string[]> => {
        try {
            const response = await api.get<string[]>(`/admin/config/ai/models/${provider}`);
            return response.data;
        } catch (error: any) {
            console.error('[AdminService] Failed to fetch models:', error);
            throw new Error(error.response?.data?.detail || 'Failed to fetch models');
        }
    },

    /**
     * Get all feature flags
     * Requires admin authentication
     */
    fetchFeatureFlags: async (): Promise<FeatureFlags> => {
        try {
            const response = await api.get<FeatureFlags>('/admin/config/features');
            return response.data;
        } catch (error: any) {
            console.error('[AdminService] Failed to fetch feature flags:', error);
            throw new Error(error.response?.data?.detail || 'Failed to fetch feature flags');
        }
    },

    /**
     * Toggle a feature flag
     * Requires admin authentication
     */
    toggleFeature: async (featureName: string, enabled: boolean): Promise<{ status: string; feature: string; enabled: boolean }> => {
        try {
            const response = await api.post(`/admin/config/features/${featureName}/toggle?enabled=${enabled}`);
            return response.data;
        } catch (error: any) {
            console.error('[AdminService] Failed to toggle feature:', error);
            throw new Error(error.response?.data?.detail || 'Failed to toggle feature');
        }
    },

    /**
     * Clear configuration cache
     * Requires admin authentication
     */
    clearConfigCache: async (): Promise<{ status: string; message: string }> => {
        try {
            const response = await api.post('/admin/config/cache/clear');
            return response.data;
        } catch (error: any) {
            console.error('[AdminService] Failed to clear cache:', error);
            throw new Error(error.response?.data?.detail || 'Failed to clear cache');
        }
    },

    // ============================================================
    // Context Management
    // ============================================================

    /**
     * Fetch all schema contexts
     * Requires admin authentication
     */
    fetchContexts: async (): Promise<ContextItem[]> => {
        try {
            const response = await api.get('/admin/contexts');
            return response.data.contexts || [];
        } catch (error: any) {
            console.error('[AdminService] Failed to fetch contexts:', error);
            throw new Error(error.response?.data?.detail || 'Failed to fetch contexts');
        }
    },

    /**
     * Create new context
     * Requires admin authentication
     */
    createContext: async (context: Omit<ContextItem, 'id'>): Promise<ContextItem> => {
        try {
            const response = await api.post('/admin/contexts', context);
            return response.data;
        } catch (error: any) {
            console.error('[AdminService] Failed to create context:', error);
            throw new Error(error.response?.data?.detail || 'Failed to create context');
        }
    },

    /**
     * Update existing context
     * Requires admin authentication
     */
    updateContext: async (contextId: number, updates: Partial<ContextItem>): Promise<ContextItem> => {
        try {
            const response = await api.put(`/admin/contexts/${contextId}`, updates);
            return response.data;
        } catch (error: any) {
            console.error('[AdminService] Failed to update context:', error);
            throw new Error(error.response?.data?.detail || 'Failed to update context');
        }
    },

    /**
     * Delete context
     * Requires admin authentication
     */
    deleteContext: async (contextId: number): Promise<void> => {
        try {
            await api.delete(`/admin/contexts/${contextId}`);
        } catch (error: any) {
            console.error('[AdminService] Failed to delete context:', error);
            throw new Error(error.response?.data?.detail || 'Failed to delete context');
        }
    }
};

export default adminService;
