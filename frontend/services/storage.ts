import * as SecureStore from 'expo-secure-store';
import { Platform } from 'react-native';

export const storage = {
    getItem: async (key: string): Promise<string | null> => {
        if (Platform.OS === 'web') {
            try {
                if (typeof localStorage !== 'undefined') {
                    return localStorage.getItem(key);
                }
            } catch (e) {
                console.error('Local storage is not available:', e);
            }
            return null;
        } else {
            return await SecureStore.getItemAsync(key);
        }
    },

    setItem: async (key: string, value: string): Promise<void> => {
        if (Platform.OS === 'web') {
            try {
                if (typeof localStorage !== 'undefined') {
                    localStorage.setItem(key, value);
                }
            } catch (e) {
                console.error('Local storage is not available:', e);
            }
        } else {
            await SecureStore.setItemAsync(key, value);
        }
    },

    removeItem: async (key: string): Promise<void> => {
        if (Platform.OS === 'web') {
            try {
                if (typeof localStorage !== 'undefined') {
                    localStorage.removeItem(key);
                }
            } catch (e) {
                console.error('Local storage is not available:', e);
            }
        } else {
            await SecureStore.deleteItemAsync(key);
        }
    }
};
