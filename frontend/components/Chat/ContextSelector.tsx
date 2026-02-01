import React from 'react';
import { View, Text, TouchableOpacity } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

export type DataContext = 'auto' | 'revenue' | 'expense';

interface ContextSelectorProps {
    context: DataContext;
    onSelect: (context: DataContext) => void;
}

const contextConfig = {
    auto: {
        label: 'Auto',
        icon: 'flash' as const,
        color: '#8B5CF6', // purple
        description: 'ตรวจจับอัตโนมัติ'
    },
    revenue: {
        label: 'รายได้',
        icon: 'trending-up' as const,
        color: '#10B981', // green
        description: 'ข้อมูลรายได้'
    },
    expense: {
        label: 'ค่าใช้จ่าย',
        icon: 'trending-down' as const,
        color: '#EF4444', // red
        description: 'ข้อมูลค่าใช้จ่าย'
    }
};

export const ContextSelector = ({ context, onSelect }: ContextSelectorProps) => {
    return (
        <View className="flex-row bg-gray-100 dark:bg-gray-800 rounded-full p-1 border border-gray-200 dark:border-gray-700">
            {(Object.keys(contextConfig) as DataContext[]).map((ctx) => {
                const config = contextConfig[ctx];
                const isSelected = context === ctx;

                return (
                    <TouchableOpacity
                        key={ctx}
                        onPress={() => onSelect(ctx)}
                        className={`px-2.5 py-1.5 rounded-full flex-row items-center gap-1 ${
                            isSelected ? 'bg-white dark:bg-gray-600 shadow-sm' : ''
                        }`}
                    >
                        <Ionicons
                            name={config.icon}
                            size={14}
                            color={isSelected ? config.color : '#9CA3AF'}
                        />
                        <Text
                            className={`text-xs font-medium ${
                                isSelected
                                    ? 'text-gray-900 dark:text-white'
                                    : 'text-gray-500 dark:text-gray-400'
                            }`}
                        >
                            {config.label}
                        </Text>
                    </TouchableOpacity>
                );
            })}
        </View>
    );
};

// Badge component to show current context in chat
export const ContextBadge = ({ context }: { context: DataContext }) => {
    const config = contextConfig[context];

    return (
        <View
            className="flex-row items-center gap-1 px-2 py-1 rounded-full"
            style={{ backgroundColor: `${config.color}20` }}
        >
            <Ionicons name={config.icon} size={12} color={config.color} />
            <Text style={{ color: config.color }} className="text-xs font-medium">
                {config.label}
            </Text>
        </View>
    );
};
