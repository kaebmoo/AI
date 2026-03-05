import api from './api';

export interface ChatRequest {
    question: string;
    session_id?: string;
    conversation_id?: string;
    provider?: string;
    context?: string;  // 'revenue' | 'expense' | undefined (auto-detect)
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

export interface ConfidenceFactor {
    name: string;
    score: number;
    max: number;
    detail: string;
}

export interface Confidence {
    score: number;
    level: string;
    level_th: string;
    color: string;
    factors: ConfidenceFactor[];
    recommendation: string;
}

export interface ChartConfig {
    category_column?: string;
    measure_column?: string;
    series_column?: string;
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
    confidence?: Confidence;           // Confidence score from validation MCP
    visualization?: string;            // AI recommended visualization type
    chart_config?: ChartConfig;        // AI recommended chart columns
    display_hint?: 'hierarchical' | 'crosstab' | 'flat'; // AI recommended table display mode
    hierarchy_columns?: string[];      // Ordered column names for hierarchical display (parent→child)
}

export interface TrainingRequest {
    question: string;
    sql: string;
    context?: string;
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
    },

    train: async (payload: TrainingRequest) => {
        const response = await api.post<{ success: boolean; message: string }>('/chat/train', payload);
        return response.data;
    }
};
