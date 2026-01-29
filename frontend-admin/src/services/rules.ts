import api from './api';

export interface BusinessRule {
    id: number;
    rule_code: string;
    rule_name: string;
    rule_description?: string;
    example_correct?: string;
    example_wrong?: string;
    severity: 'error' | 'warning' | 'info';
    is_active: boolean;
    created_at: string;
    updated_at?: string;
}

export interface BusinessRuleCreate {
    rule_code: string;
    rule_name: string;
    rule_description?: string;
    example_correct?: string;
    example_wrong?: string;
    severity: 'error' | 'warning' | 'info';
    is_active?: boolean;
}

export interface BusinessRuleUpdate {
    rule_code?: string;
    rule_name?: string;
    rule_description?: string;
    example_correct?: string;
    example_wrong?: string;
    severity?: 'error' | 'warning' | 'info';
    is_active?: boolean;
}

export interface BusinessRuleListResponse {
    rules: BusinessRule[];
    total: number;
}

export const getRules = async (params?: { severity?: string; is_active?: boolean }) => {
    const response = await api.get<BusinessRuleListResponse>('/admin/rules', { params });
    return response.data;
};

export const getRule = async (id: number) => {
    const response = await api.get<BusinessRule>(`/admin/rules/${id}`);
    return response.data;
};

export const createRule = async (data: BusinessRuleCreate) => {
    const response = await api.post<BusinessRule>('/admin/rules', data);
    return response.data;
};

export const updateRule = async (id: number, data: BusinessRuleUpdate) => {
    const response = await api.put<BusinessRule>(`/admin/rules/${id}`, data);
    return response.data;
};

export const deleteRule = async (id: number) => {
    await api.delete(`/admin/rules/${id}`);
};

export const toggleRule = async (id: number) => {
    const response = await api.post<BusinessRule>(`/admin/rules/${id}/toggle`);
    return response.data;
};
