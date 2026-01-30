import axios from 'axios';

// Use same base URL as other services or from environment
const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1';

const getAuthHeader = () => {
    const token = localStorage.getItem('token');
    return { Authorization: `Bearer ${token}` };
};

export const adminService = {
    refreshCache: async () => {
        const response = await axios.post(`${API_URL}/admin/refresh-cache`, {}, {
            headers: getAuthHeader()
        });
        return response.data;
    },

    getStats: async () => {
        const response = await axios.get(`${API_URL}/admin/stats`, {
            headers: getAuthHeader()
        });
        return response.data;
    }
};
