import api from './api';

export interface ConversationItem {
    id: string;
    title: string | null;
    updated_at: string | null;
    message_count: number;
    preview: string | null;
}

export interface ConversationListResponse {
    items: ConversationItem[];
    total: number;
    page: number;
    page_size: number;
}

export interface ConversationMessage {
    id: number;
    question: string;
    ai_response: string | null;
    created_at: string | null;
    generated_sql: string | null;
    sql_result_summary: string | null;
    tokens_used: number;
    context_name: string | null;
    is_bookmarked: boolean;
    feedback_rating: number | null;
    execution_time_ms: number;
}

export interface ConversationDetail {
    id: string;
    title: string | null;
    created_at: string | null;
    updated_at: string | null;
    message_count: number;
    messages: ConversationMessage[];
}

export const conversationService = {
    list: async (page = 1, pageSize = 20, search?: string) => {
        const params: Record<string, any> = { page, page_size: pageSize };
        if (search) params.search = search;
        const response = await api.get<ConversationListResponse>('/conversations', { params });
        return response.data;
    },

    get: async (conversationId: string) => {
        const response = await api.get<ConversationDetail>(`/conversations/${conversationId}`);
        return response.data;
    },

    create: async () => {
        const response = await api.post<{ id: string; title: string | null; created_at: string }>('/conversations');
        return response.data;
    },

    update: async (conversationId: string, data: { title?: string; is_archived?: boolean }) => {
        const response = await api.patch<{ id: string; title: string | null; updated_at: string }>(
            `/conversations/${conversationId}`,
            data
        );
        return response.data;
    },

    delete: async (conversationId: string) => {
        const response = await api.delete<{ success: boolean }>(`/conversations/${conversationId}`);
        return response.data;
    },
};
