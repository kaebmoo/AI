import axios from 'axios';
import { storage } from './storage';
import { Platform } from 'react-native';

// Use localhost for iOS simulator, 10.0.2.2 for Android emulator, localhost for Web
const DEV_API_URL = Platform.select({
    ios: 'http://localhost:8000/api/v1',
    android: 'http://10.0.2.2:8000/api/v1',
    web: 'http://localhost:8000/api/v1',
    default: 'http://localhost:8000/api/v1',
});

const resolveApiBaseUrl = () => {
    const configuredUrl = process.env.EXPO_PUBLIC_API_URL?.trim();
    if (configuredUrl) {
        return configuredUrl.replace(/\/$/, '');
    }

    if (process.env.NODE_ENV !== 'production') {
        return DEV_API_URL;
    }

    throw new Error('EXPO_PUBLIC_API_URL must be configured for production builds.');
};

export const API_BASE_URL = resolveApiBaseUrl();

const api = axios.create({
    baseURL: API_BASE_URL,
    headers: {
        'Content-Type': 'application/json',
    },
});

// Interceptor to add session token
api.interceptors.request.use(async (config) => {
    try {
        const token = await storage.getItem('session_token');
        if (token) {
            config.headers['X-Session-Token'] = token;
        }
        console.log(`[API] ${config.method?.toUpperCase()} ${config.url}`, config.data);
    } catch (error) {
        console.error('Error reading token', error);
    }
    return config;
});

// Response interceptor
api.interceptors.response.use(
    (response) => response,
    async (error) => {
        if (error.response?.status === 401) {
            console.log('[API] 401 Unauthorized - Redirecting to login');
            await storage.removeItem('session_token');

            // Emit event so AuthContext can update state
            const { authEvents } = require('./authEvent');
            authEvents.emitSignOut();
        }
        return Promise.reject(error);
    }
);

export default api;
