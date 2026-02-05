import api from './api';

export interface ContextItem {
    id?: number | string;
    name: string;
    display_name: string;
    description?: string;
    keywords?: string[];
    is_active?: boolean;
    icon?: string;
    color?: string;
}

export const contextService = {
    /**
     * Fetch all available contexts from backend
     */
    fetchContexts: async (): Promise<ContextItem[]> => {
        try {
            const response = await api.get<ContextItem[]>('/chat/contexts');
            return response.data;
        } catch (error) {
            console.error('Failed to fetch contexts:', error);
            // Return fallback if API fails
            return [
                { name: 'revenue', display_name: 'รายได้', description: 'ข้อมูลรายได้' },
                { name: 'expense', display_name: 'ค่าใช้จ่าย', description: 'ข้อมูลค่าใช้จ่าย' }
            ];
        }
    },

    /**
     * Force refresh metadata cache on backend
     */
    refreshMetadata: async (): Promise<{ message: string }> => {
        const response = await api.post('/chat/refresh');
        return response.data;
    }
};
