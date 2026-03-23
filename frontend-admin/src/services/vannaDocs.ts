import api from './api';

export interface VannaDoc {
    id: number;
    doc_key: string;
    title: string;
    content: string;
    category: string;
    context_name: string | null;
    is_active: boolean;
    created_at: string;
    updated_at?: string;
}

export interface VannaDocCreate {
    doc_key: string;
    title: string;
    content: string;
    category?: string;
    context_name?: string | null;
}

export interface VannaDocUpdate {
    title?: string;
    content?: string;
    category?: string;
    context_name?: string | null;
    is_active?: boolean;
}

export interface VannaDocListResponse {
    docs: VannaDoc[];
    total: number;
}

export interface BrainSyncStatus {
    last_brain_sync_at: string | null;
    last_brain_relevant_change_at: string | null;
    needs_sync: boolean;
}

export const getVannaDocs = async (params?: { category?: string; is_active?: boolean }) => {
    const response = await api.get<VannaDocListResponse>('/admin/vanna-docs', { params });
    return response.data;
};

export const getVannaDoc = async (id: number) => {
    const response = await api.get<VannaDoc>(`/admin/vanna-docs/${id}`);
    return response.data;
};

export const createVannaDoc = async (data: VannaDocCreate) => {
    const response = await api.post<VannaDoc>('/admin/vanna-docs', data);
    return response.data;
};

export const updateVannaDoc = async (id: number, data: VannaDocUpdate) => {
    const response = await api.put<VannaDoc>(`/admin/vanna-docs/${id}`, data);
    return response.data;
};

export const deleteVannaDoc = async (id: number) => {
    await api.delete(`/admin/vanna-docs/${id}`);
};

export const getBrainSyncStatus = async () => {
    const response = await api.get<BrainSyncStatus>('/admin/brain-sync-status');
    return response.data;
};
