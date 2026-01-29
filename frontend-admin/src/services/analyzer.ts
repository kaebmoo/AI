import api from './api';
import type { SchemaMetadata } from './schema';
import type { SemanticMapping } from './mappings';
import type { BusinessRule } from './rules';

export interface ColumnInfo {
    name: string;
    sample_values: any[];
    dtype: string;
}

export interface AnalysisRequest {
    columns: ColumnInfo[];
    db_type: string;
}

export interface AnalysisResult {
    metadata: SchemaMetadata[];
    mappings: SemanticMapping[];
    rules: BusinessRule[];
}

export interface ImportRequest {
    table_name: string;
    metadata: SchemaMetadata[];
    mappings: SemanticMapping[];
    rules: BusinessRule[];
}

// Upload file for analysis
export const uploadFile = async (file: File) => {
    const formData = new FormData();
    formData.append('file', file);

    // Note: sending multipart/form-data
    const response = await api.post<AnalysisRequest>('/admin/analyzer/analyze/upload', formData, {
        headers: {
            'Content-Type': 'multipart/form-data',
        },
    });
    return response.data;
};

export const analyzeText = async (content: string, table_name: string) => {
    const response = await api.post<AnalysisRequest>('/admin/analyzer/analyze/text', { content, table_name });
    return response.data;
};

// Get AI suggestions
export const getAISuggestions = async (data: AnalysisRequest) => {
    const response = await api.post<AnalysisResult>('/admin/analyzer/analyze/ai-suggest', data);
    return response.data;
};

// Import schema
export const importSchema = async (data: ImportRequest) => {
    const response = await api.post<{ status: string, message: string }>('/admin/analyzer/analyze/import', data);
    return response.data;
};
