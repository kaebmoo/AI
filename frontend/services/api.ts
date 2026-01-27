import axios from 'axios';
import { storage } from './storage';
import { Platform } from 'react-native';

// Use localhost for iOS simulator, 10.0.2.2 for Android emulator
const DEV_API_URL = Platform.select({
    ios: 'http://localhost:8000/api/v1',
    android: 'http://10.0.2.2:8000/api/v1',
    default: 'http://localhost:8000/api/v1',
});

const api = axios.create({
    baseURL: process.env.EXPO_PUBLIC_API_URL || DEV_API_URL,
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
    } catch (error) {
        console.error('Error reading token', error);
    }
    return config;
});

export default api;
