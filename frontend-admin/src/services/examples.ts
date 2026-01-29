import api from './api';

export interface GoldenExample {
    id: number;
    question_pattern: string;
    expected_sql: string;
    category?: string;
    is_active: boolean;
    added_by: number;
    usage_count: number;
    created_at: string;
    updated_at?: string;
}

export interface GoldenExampleCreate {
    question_pattern: string;
    expected_sql: string;
    category?: string;
    is_active?: boolean;
}

export interface GoldenExampleUpdate {
    question_pattern?: string;
    expected_sql?: string;
    category?: string;
    is_active?: boolean;
}

export interface GoldenExampleListResponse {
    examples: GoldenExample[];
    total: number;
    categories: string[];
}

export const getExamples = async (params?: { category?: string; is_active?: boolean }) => {
    const response = await api.get<GoldenExampleListResponse>('/admin/golden-examples', { params });
    return response.data;
};

export const getExampleCategories = async () => {
    const response = await api.get<string[]>('/admin/golden-examples/categories');
    return response.data;
};

export const createExample = async (data: GoldenExampleCreate) => {
    const response = await api.post<GoldenExample>('/admin/golden-examples', data);
    return response.data;
};

export const updateExample = async (id: number, data: GoldenExampleUpdate) => {
    const response = await api.put<GoldenExample>(`/admin/golden-examples/${id}`, data);
    return response.data;
};

export const deleteExample = async (id: number) => {
    await api.delete(`/admin/golden-examples/${id}`);
};
