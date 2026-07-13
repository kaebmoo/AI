import api, { API_BASE_URL } from './api';
import type { ChartSpec } from '../types/chart';

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
    // Extended fields from enrich_chart_config
    suggested_type?: string;
    available_types?: string[];
    column_roles?: Array<{
        column: string;
        role: 'category' | 'measure' | 'series' | 'secondary_measure';
        label?: string;
        format?: 'number' | 'currency_thb' | 'percent' | 'date';
        axis?: 'left' | 'right';
    }>;
    title?: string;
    sort_by?: string;
    show_data_labels?: boolean;
    warning?: string;
    is_time_axis?: boolean;
    max_series?: number;
    chart_spec?: ChartSpec;
}

export interface ChatResponse {
    id?: number;
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
    is_chart_only?: boolean;           // True when chart-only re-render (no SQL re-executed)
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
    onDone?: (id: number | undefined, conversationId: string) => void;
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
        const baseURL = api.defaults.baseURL || API_BASE_URL;

        // Total-request timeout: the backend sends keepalive comments so the
        // socket stays busy even if the query hangs — an idle timeout wouldn't
        // fire. Cap the whole request so a hang surfaces as an error, not a
        // stuck "⏳". gotResult guards against aborting a nearly-done stream.
        const controller = new AbortController();
        let gotResult = false;
        const timeout = setTimeout(() => { if (!gotResult) controller.abort(); }, 180000);

        try {
            const response = await fetch(`${baseURL}/chat/stream`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Session-Token': token || '',
                },
                body: JSON.stringify(payload),
                signal: controller.signal,
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
                                    gotResult = true;
                                    callbacks.onAnswer?.(data as ChatResponse);
                                    break;
                                case 'done':
                                    callbacks.onDone?.(data.id, data.conversation_id);
                                    break;
                                case 'error':
                                    gotResult = true;
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

            // Stream ended without an answer OR error event (dropped connection,
            // backend closed early) — never leave the chat silently waiting.
            if (!gotResult) {
                callbacks.onError?.('ไม่ได้รับคำตอบจากเซิร์ฟเวอร์ (การเชื่อมต่ออาจถูกตัด) — กรุณาลองใหม่');
            }
        } catch (err: any) {
            console.error('SSE streaming error:', err);
            if (controller.signal.aborted) {
                callbacks.onError?.('คำขอใช้เวลานานเกินไป (timeout) — กรุณาลองใหม่');
            } else {
                // Network-level failure before/around the SSE stream → try the
                // plain endpoint once; if THAT fails too, surface it (never swallow).
                try {
                    callbacks.onStatus?.('generating', 'Processing...');
                    const response = await chatService.sendMessage(payload);
                    callbacks.onAnswer?.(response);
                    callbacks.onDone?.(response.id, response.conversation_id);
                } catch (fallbackErr: any) {
                    console.error('Fallback request also failed:', fallbackErr);
                    const msg = fallbackErr?.response?.data?.detail || fallbackErr?.message || 'ไม่สามารถเชื่อมต่อเซิร์ฟเวอร์ได้';
                    callbacks.onError?.(msg);
                }
            }
        } finally {
            clearTimeout(timeout);
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
