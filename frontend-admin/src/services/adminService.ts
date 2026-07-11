import axios from 'axios';
import { API_URL } from './api';

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
    // F9 — agentic latency (default OFF; enable only with measurements, see plan/RESULT_F9.md)
    template_answers_enabled: boolean;
    intent_state_enabled: boolean;
    escalation_ladder_enabled: boolean;
    escalation_tool_loop_enabled: boolean;
    query_latency_budget_s: number;
}

export interface DashboardAlert {
    level: 'info' | 'warning' | 'success';
    title: string;
    message: string;
    href?: string;
}

export interface DashboardContextUsage {
    context_name: string;
    count: number;
}

export interface DashboardPendingReview {
    id: number;
    question: string;
    rating: string | null;
    created_at: string | null;
}

export interface EffectiveAIState {
    default_provider: {
        id: string;
        name: string;
        display_name: string;
        is_active: boolean;
    };
    default_model: {
        id: string;
        display_name: string;
        is_active: boolean;
        tier: string;
    };
    provider_source: string;
    fallback_in_use: boolean;
    provider_alignment: boolean;
    model_alignment: boolean;
    active_provider_count: number;
    total_provider_count: number;
    active_model_count: number;
    total_model_count: number;
    active_providers: AIProvider[];
    enabled_features: string[];
    feature_flags: FeatureFlags;
    last_brain_sync_at: string | null;
}

export interface DashboardOverview {
    generated_at: string;
    effective_ai: EffectiveAIState;
    usage: {
        total_queries_7d: number;
        error_count_7d: number;
        error_rate_7d: number;
        avg_execution_time_ms_7d: number;
        avg_tokens_used_7d: number;
        top_contexts_7d: DashboardContextUsage[];
    };
    feedback: {
        total_feedback_30d: number;
        thumbs_up_30d: number;
        thumbs_down_30d: number;
        satisfaction_rate_30d: number;
        pending_reviews: number;
        pending_review_items: DashboardPendingReview[];
        trending_queries_7d: Array<{ question: string; count: number }>;
        category_breakdown: Record<string, number>;
    };
    data_admin: {
        total_users: number;
        total_mappings: number;
        total_rules: number;
        total_columns: number;
        total_contexts: number;
        active_contexts: number;
        active_warnings: number;
        active_patterns: number;
    };
    alerts: DashboardAlert[];
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

    getDashboardOverview: async (): Promise<DashboardOverview> => {
        const response = await axios.get(`${API_URL}/admin/dashboard-overview`, {
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

    getEffectiveAIConfig: async (): Promise<EffectiveAIState> => {
        const response = await axios.get(`${API_URL}/admin/config/ai/effective`, {
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

    setNumericConfig: async (key: string, value: number) => {
        const response = await axios.put(
            `${API_URL}/admin/config/settings/${key}?value=${value}`,
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

    clearQueryCache: async () => {
        const response = await axios.post(`${API_URL}/admin/clear-query-cache`, {}, {
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
