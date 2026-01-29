import api from './api'
import type { LoginRequest, LoginResponse } from '../types/index'

export const authService = {
    login: async (data: LoginRequest): Promise<LoginResponse> => {
        const response = await api.post('/auth/login', data)
        return response.data
    },

    logout: async () => {
        await api.post('/auth/logout')
        localStorage.removeItem('token')
        localStorage.removeItem('user')
    },

    getCurrentUser: () => {
        try {
            const userStr = localStorage.getItem('user')
            return userStr ? JSON.parse(userStr) : null
        } catch (e) {
            console.error("Failed to parse user from local storage", e);
            localStorage.removeItem('user');
            return null;
        }
    }
}
