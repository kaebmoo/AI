import axios from 'axios';
import type { SchemaContext, SchemaContextCreate, SchemaContextUpdate } from '../types/schemaContext';

// Use same base URL as other services or from environment
const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1';

const getAuthHeader = () => {
    const token = localStorage.getItem('token');
    return { Authorization: `Bearer ${token}` };
};

export const contextService = {
    getAll: async () => {
        const response = await axios.get(`${API_URL}/admin/contexts`, {
            headers: getAuthHeader()
        });
        return response.data;
    },

    create: async (data: SchemaContextCreate) => {
        const response = await axios.post(`${API_URL}/admin/contexts`, data, {
            headers: getAuthHeader()
        });
        return response.data;
    },

    update: async (id: number, data: SchemaContextUpdate) => {
        const response = await axios.put(`${API_URL}/admin/contexts/${id}`, data, {
            headers: getAuthHeader()
        });
        return response.data;
    },

    delete: async (id: number) => {
        await axios.delete(`${API_URL}/admin/contexts/${id}`, {
            headers: getAuthHeader()
        });
    }
};
