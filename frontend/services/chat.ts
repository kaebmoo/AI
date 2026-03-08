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

export type FeedbackRating = 'thumbs_up' | 'thumbs_down';
export type FeedbackCategory = 'wrong_data' | 'incomplete' | 'hard_to_understand' | 'slow' | 'sql_error' | 'perfect' | 'other';

export interface FeedbackRequest {
    rating: FeedbackRating;
    category?: FeedbackCategory;
    feedback_text?: string;
}

export interface SSECallbacks {
    onStatus?: (status: string, message: string) => void;
    onDataReady?: (data: any[], sqlQuery: string) => void;
    onAnswer?: (response: ChatResponse) => void;
    onDone?: (id: number, conversationId: string) => void;
    onError?: (error: string) => void;
}

export const chatService = {
    sendMessage: async (payload: ChatRequest) => {
        console.log('Sending message to chat service:', payload);
        const response = await api.post<ChatResponse>('/chat', payload);
        return response.data;
    },

    /**
     * Stream chat response via SSE.
     * Events: status → data_ready → answer → done
     * Falls back to sendMessage if streaming fails.
     */
    streamMessage: async (payload: ChatRequest, callbacks: SSECallbacks) => {
        const { storage } = require('./storage');
        const token = await storage.getItem('session_token');
        const baseURL = api.defaults.baseURL || 'http://localhost:8000/api/v1';

        try {
            const response = await fetch(`${baseURL}/chat/stream`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Session-Token': token || '',
                },
                body: JSON.stringify(payload),
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }

            const reader = response.body?.getReader();
            if (!reader) {
                throw new Error('ReadableStream not supported');
            }

            const decoder = new TextDecoder();
            let buffer = '';
            let currentEvent = ''; // Persist across chunks — event: and data: may arrive in different TCP segments

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });

                // Parse SSE events from buffer
                const lines = buffer.split('\n');
                buffer = lines.pop() || ''; // Keep incomplete line in buffer

                for (const line of lines) {
                    if (line.startsWith('event: ')) {
                        currentEvent = line.slice(7).trim();
                    } else if (line.startsWith('data: ') && currentEvent) {
                        try {
                            const data = JSON.parse(line.slice(6));
                            switch (currentEvent) {
                                case 'status':
                                    callbacks.onStatus?.(data.status, data.message);
                                    break;
                                case 'data_ready':
                                    callbacks.onDataReady?.(data.data, data.sql_query);
                                    break;
                                case 'answer':
                                    callbacks.onAnswer?.(data as ChatResponse);
                                    break;
                                case 'done':
                                    callbacks.onDone?.(data.id, data.conversation_id);
                                    break;
                                case 'error':
                                    callbacks.onError?.(data.message);
                                    break;
                            }
                            currentEvent = '';
                        } catch (parseErr) {
                            // JSON parse failed — data line may be split across chunks
                            // Keep currentEvent and let buffer accumulate
                            console.debug('SSE: partial data, waiting for next chunk');
                        }
                    } else if (line === '' || line.startsWith(':')) {
                        // Empty line (event separator) or comment (keepalive) — skip
                    }
                }
            }
        } catch (err: any) {
            console.warn('SSE streaming failed, falling back to regular API:', err.message);
            // Fallback to regular request
            callbacks.onStatus?.('generating', 'Processing...');
            const response = await chatService.sendMessage(payload);
            callbacks.onAnswer?.(response);
            callbacks.onDone?.(response.id, response.conversation_id);
        }
    },

    getHistory: async () => {
        const response = await api.get<ChatResponse[]>('/chat/history');
        return response.data;
    },

    train: async (payload: TrainingRequest) => {
        const response = await api.post<{ success: boolean; message: string }>('/chat/train', payload);
        return response.data;
    },

    submitFeedback: async (chatId: number, payload: FeedbackRequest) => {
        const response = await api.post<{ message: string; id: number }>(
            `/feedback/${chatId}`,
            null,
            { params: payload }
        );
        return response.data;
    },
};
