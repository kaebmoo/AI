import api from './api';

export interface HierarchyLevel {
    context_name: string;
    level: number;
    level_label_th: string;
    level_label_en: string;
    level_columns: string[];
    detection_keywords: string[];
    source: string;
    is_active: boolean;
    value_count: number;
}

export interface HierarchyValue {
    id: number;
    context_name: string;
    level: number;
    value: string;
    parent_value: string | null;
    aliases: string[];
    source: string;
    is_active: boolean;
    children_count: number;
}

export interface HierarchyContextSummary {
    context_name: string;
    level_count: number;
    value_count: number;
    manual_count: number;
    auto_count: number;
}

export interface HierarchyDiff {
    context_name: string;
    new_values: { level: number; value: string; change_type: string }[];
    missing_values: { level: number; value: string; change_type: string }[];
    unchanged_count: number;
}

export interface UnmatchedKeyword {
    keyword: string;
    context_name: string;
    occurrence_count: number;
    last_question: string | null;
}

// --- Context & Levels ---

export const getContexts = () =>
    api.get<HierarchyContextSummary[]>('/admin/hierarchy');

export const getLevels = (context: string) =>
    api.get<HierarchyLevel[]>(`/admin/hierarchy/${context}/levels`);

export const upsertLevel = (context: string, data: Partial<HierarchyLevel> & { level: number }) =>
    api.post(`/admin/hierarchy/${context}/levels`, data);

export const updateLevel = (context: string, level: number, data: Partial<HierarchyLevel>) =>
    api.put(`/admin/hierarchy/${context}/levels/${level}`, data);

export const deleteLevel = (context: string, level: number) =>
    api.delete(`/admin/hierarchy/${context}/levels/${level}`);

// --- Values ---

export const getValues = (context: string, params?: {
    level?: number; parent_value?: string; search?: string; page?: number; page_size?: number;
}) => api.get(`/admin/hierarchy/${context}/values`, { params });

export const createValue = (context: string, data: {
    level: number; value: string; parent_value?: string; aliases?: string[];
}) => api.post(`/admin/hierarchy/${context}/values`, data);

export const updateValue = (id: number, data: {
    value?: string; parent_value?: string; aliases?: string[];
}) => api.put(`/admin/hierarchy/values/${id}`, data);

export const deleteValue = (id: number) =>
    api.delete(`/admin/hierarchy/values/${id}`);

// --- Extract & Sync ---

export const extractHierarchy = (context?: string) =>
    api.post('/admin/hierarchy/extract', null, { params: context ? { context_name: context } : {} });

export const getDiff = (context: string) =>
    api.get<HierarchyDiff>(`/admin/hierarchy/${context}/diff`);

// --- Bootstrap & Views ---

export interface AvailableView {
    context_name: string;
    view_name: string;
    display_name: string;
    source: string;
}

export const getAvailableViews = () =>
    api.get<AvailableView[]>('/admin/hierarchy/views');

export const bootstrapHierarchy = (context_name: string, view_name: string) =>
    api.post('/admin/hierarchy/bootstrap', null, { params: { context_name, view_name } });

// --- CSV Import ---

export const importCsv = (context: string, file: File, params: {
    level: number; value_column: string; parent_column?: string; alias_columns?: string;
}) => {
    const formData = new FormData();
    formData.append('file', file);
    return api.post(`/admin/hierarchy/${context}/import-csv`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
        params,
    });
};

// --- Unmatched Keywords ---

export const getUnmatchedKeywords = (context?: string) =>
    api.get<UnmatchedKeyword[]>('/admin/hierarchy/unmatched', { params: context ? { context_name: context } : {} });

export const resolveUnmatched = (keyword: string, context: string) =>
    api.post(`/admin/hierarchy/unmatched/${encodeURIComponent(keyword)}/resolve`, null, { params: { context_name: context } });
