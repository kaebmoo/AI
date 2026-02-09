import React, { useState, useEffect } from 'react';
import { View, Text, TouchableOpacity, ActivityIndicator } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../services/api';

interface Provider {
    id: string;
    name: string;
    display_name: string;
    model: string;
    icon: string;
    is_default: boolean;
}

interface ModelSelectorProps {
    provider: string;
    onSelect: (provider: string) => void;
}

// Icon mapping (Ionicons names)
const iconMap: Record<string, any> = {
    'sparkles': 'sparkles',
    'bulb': 'bulb',
    'leaf': 'leaf',
    'flash': 'flash',
    'hardware-chip': 'hardware-chip'
};

// Color mapping (for active state)
const colorMap: Record<string, string> = {
    'claude': '#D97706',   // Amber
    'gemini': '#2563EB',   // Blue
    'matcha': '#059669'    // Green
};

export const ModelSelector = ({ provider, onSelect }: ModelSelectorProps) => {
    const [providers, setProviders] = useState<Provider[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        fetchProviders();
    }, []);

    const fetchProviders = async () => {
        try {
            setLoading(true);
            setError(null);

            const response = await api.get('/admin/config/ai/providers');
            const fetchedProviders = response.data || [];

            setProviders(fetchedProviders);

            // If current provider is not in the list, select the default
            if (fetchedProviders.length > 0) {
                const isCurrentProviderAvailable = fetchedProviders.some(
                    (p: Provider) => p.id === provider
                );

                if (!isCurrentProviderAvailable) {
                    const defaultProvider = fetchedProviders.find((p: Provider) => p.is_default);
                    if (defaultProvider) {
                        onSelect(defaultProvider.id);
                    } else {
                        onSelect(fetchedProviders[0].id);
                    }
                }
            }

        } catch (err: any) {
            console.error('[ModelSelector] Failed to fetch providers:', err);
            setError(err.response?.data?.detail || 'Failed to load AI models');

            // Fallback to default providers if API fails
            setProviders([
                { id: 'matcha', name: 'Matcha', display_name: 'Matcha', model: 'gpt-4.1', icon: 'leaf', is_default: true }
            ]);

        } finally {
            setLoading(false);
        }
    };

    if (loading) {
        return (
            <View className="flex-row bg-gray-100 dark:bg-gray-800 rounded-full p-2 border border-gray-200 dark:border-gray-700">
                <ActivityIndicator size="small" color="#9CA3AF" />
                <Text className="text-xs text-gray-500 dark:text-gray-400 ml-2">Loading models...</Text>
            </View>
        );
    }

    if (error) {
        return (
            <View className="flex-row bg-red-50 dark:bg-red-900/20 rounded-full p-2 border border-red-200 dark:border-red-800">
                <Ionicons name="alert-circle" size={14} color="#DC2626" />
                <Text className="text-xs text-red-600 dark:text-red-400 ml-2">{error}</Text>
            </View>
        );
    }

    if (providers.length === 0) {
        return (
            <View className="flex-row bg-yellow-50 dark:bg-yellow-900/20 rounded-full p-2 border border-yellow-200 dark:border-yellow-800">
                <Ionicons name="warning" size={14} color="#D97706" />
                <Text className="text-xs text-yellow-700 dark:text-yellow-400 ml-2">
                    No AI models enabled. Contact admin.
                </Text>
            </View>
        );
    }

    return (
        <View className="flex-row bg-gray-100 dark:bg-gray-800 rounded-full p-1 border border-gray-200 dark:border-gray-700">
            {providers.map((p) => {
                const isActive = provider === p.id;
                const iconName = iconMap[p.icon] || 'hardware-chip';
                const activeColor = colorMap[p.id] || '#6B7280';

                return (
                    <TouchableOpacity
                        key={p.id}
                        onPress={() => onSelect(p.id)}
                        className={`px-3 py-1.5 rounded-full flex-row items-center gap-1 ${
                            isActive ? 'bg-white dark:bg-gray-600 shadow-sm' : ''
                        }`}
                    >
                        <Ionicons
                            name={iconName}
                            size={14}
                            color={isActive ? activeColor : '#9CA3AF'}
                        />
                        <Text
                            className={`text-xs font-medium ${
                                isActive
                                    ? 'text-gray-900 dark:text-white'
                                    : 'text-gray-500 dark:text-gray-400'
                            }`}
                        >
                            {p.name}
                        </Text>
                    </TouchableOpacity>
                );
            })}
        </View>
    );
};
