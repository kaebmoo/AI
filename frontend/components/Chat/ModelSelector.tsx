import React from 'react';
import { View, Text, TouchableOpacity } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

interface ModelSelectorProps {
    provider: string; // 'claude' | 'gemini'
    onSelect: (provider: string) => void;
}

export const ModelSelector = ({ provider, onSelect }: ModelSelectorProps) => {
    return (
        <View className="flex-row bg-gray-100 dark:bg-gray-800 rounded-full p-1 border border-gray-200 dark:border-gray-700">
            <TouchableOpacity
                onPress={() => onSelect('gemini')}
                className={`px-3 py-1.5 rounded-full flex-row items-center gap-1 ${provider === 'gemini' ? 'bg-white dark:bg-gray-600 shadow-sm' : ''}`}
            >
                <Ionicons name="sparkles" size={14} color={provider === 'gemini' ? '#2563EB' : '#9CA3AF'} />
                <Text className={`text-xs font-medium ${provider === 'gemini' ? 'text-gray-900 dark:text-white' : 'text-gray-500 dark:text-gray-400'}`}>
                    Gemini
                </Text>
            </TouchableOpacity>

            <TouchableOpacity
                onPress={() => onSelect('claude')}
                className={`px-3 py-1.5 rounded-full flex-row items-center gap-1 ${provider === 'claude' ? 'bg-white dark:bg-gray-600 shadow-sm' : ''}`}
            >
                <Ionicons name="bulb" size={14} color={provider === 'claude' ? '#D97706' : '#9CA3AF'} />
                <Text className={`text-xs font-medium ${provider === 'claude' ? 'text-gray-900 dark:text-white' : 'text-gray-500 dark:text-gray-400'}`}>
                    Claude
                </Text>
            </TouchableOpacity>

            <TouchableOpacity
                onPress={() => onSelect('matcha')}
                className={`px-3 py-1.5 rounded-full flex-row items-center gap-1 ${provider === 'matcha' ? 'bg-white dark:bg-gray-600 shadow-sm' : ''}`}
            >
                <Ionicons name="leaf" size={14} color={provider === 'matcha' ? '#059669' : '#9CA3AF'} />
                <Text className={`text-xs font-medium ${provider === 'matcha' ? 'text-gray-900 dark:text-white' : 'text-gray-500 dark:text-gray-400'}`}>
                    Matcha
                </Text>
            </TouchableOpacity>
        </View>
    );
};
