import api from './api';

export interface ChatRequest {
    question: string;
    session_id?: string;
    conversation_id?: string;
    provider?: string;
    max_retries?: number;
}

export interface DataWarning {
    code: string;
    message: string;
    severity: 'info' | 'warning' | 'important';
}

export interface RetryAttempt {
    attempt: number;
    error_type: string;
    error: string;
    sql?: string;
}

export interface ChatResponse {
    id: number;
    conversation_id: string;
    question: string;
    answer: string;
    sql_query?: string;
    data?: any[];
    execution_time_ms: number;
    retry_count?: number;
    retry_history?: RetryAttempt[];
    warnings?: DataWarning[];
}

export const chatService = {
    sendMessage: async (payload: ChatRequest) => {
        console.log('Sending message to chat service:', payload);
        const response = await api.post<ChatResponse>('/chat', payload);
        return response.data;
    },

    getHistory: async () => {
        const response = await api.get<ChatResponse[]>('/chat/history');
        return response.data;
    }
};
