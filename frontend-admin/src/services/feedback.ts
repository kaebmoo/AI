import api from './api';

export interface FeedbackStats {
    total_feedback: number;
    thumbs_up: number;
    thumbs_down: number;
    satisfaction_rate: number;
    category_breakdown: Record<string, number>;
    pending_reviews: number;
}

export interface PendingFeedback {
    id: number;
    chat_id: number;
    rating: string;
    feedback_text: string | null;
    created_at: string | null;
    question: string;
    ai_response: string;
}

export interface TrendingQuery {
    question: string;
    count: number;
}

export interface AdminDashboard {
    feedback_stats: FeedbackStats;
    pending_reviews: PendingFeedback[];
    trending_queries: TrendingQuery[];
    slow_queries: any[];
}

export interface ReviewRequest {
    notes?: string;
    is_golden_example?: boolean;
}

export const feedbackService = {
    getStats: async (days: number = 30) => {
        const response = await api.get<FeedbackStats>('/feedback/stats', { params: { days } });
        return response.data;
    },

    getPending: async (limit: number = 50) => {
        const response = await api.get<PendingFeedback[]>('/feedback/pending', { params: { limit } });
        return response.data;
    },

    getDashboard: async () => {
        const response = await api.get<AdminDashboard>('/feedback/admin/dashboard');
        return response.data;
    },

    getTrending: async (days: number = 7, limit: number = 10) => {
        const response = await api.get<TrendingQuery[]>('/feedback/trending', { params: { days, limit } });
        return response.data;
    },

    reviewFeedback: async (feedbackId: number, data: ReviewRequest) => {
        const response = await api.post(`/feedback/${feedbackId}/review`, data);
        return response.data;
    },

    updateTrending: async () => {
        const response = await api.post('/feedback/trending/update');
        return response.data;
    },
};
