import api from './api';

export interface ChatRequest {
    question: string;
    session_id?: string;
    conversation_id?: string;
    provider?: string;
}

export interface ChatResponse {
    id: number;
    conversation_id: string;
    question: string;
    answer: string;
    sql_query?: string;
    data?: any[]; // For now generic
    execution_time_ms: number;
}

export const chatService = {
    sendMessage: async (payload: ChatRequest) => {
        const response = await api.post<ChatResponse>('/chat/', payload);
        return response.data;
    },

    getHistory: async () => {
        const response = await api.get<ChatResponse[]>('/chat/history');
        return response.data;
    }
};
