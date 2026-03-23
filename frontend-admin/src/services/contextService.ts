import axios from 'axios';
import { API_URL } from './api';
import type { SchemaContextCreate, SchemaContextUpdate } from '../types/schemaContext';

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
