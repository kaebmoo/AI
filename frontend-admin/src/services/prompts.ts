
import api from './api';

export interface PromptVersion {
    id: number;
    version: number;
    system_prompt: string;
    notes?: string;
    created_at: string;
    created_by?: number;
    is_active: boolean;
}

export interface PromptVersionCreate {
    system_prompt: string;
    notes?: string;
}

export interface PromptVersionListResponse {
    versions: PromptVersion[];
    total: number;
}

// List all versions
export const getPromptVersions = async () => {
    const response = await api.get<PromptVersionListResponse>('/admin/prompts');
    return response.data;
};

// Create new version
export const createPromptVersion = async (data: PromptVersionCreate) => {
    const response = await api.post<PromptVersion>('/admin/prompts', data);
    return response.data;
};

// Activate version
export const activatePromptVersion = async (id: number) => {
    const response = await api.post<PromptVersion>(`/admin/prompts/${id}/activate`);
    return response.data;
};

// Get active version
export const getActivePrompt = async () => {
    const response = await api.get<PromptVersion>('/admin/prompts/active');
    return response.data;
};
