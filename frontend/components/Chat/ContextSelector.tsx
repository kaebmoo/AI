import React, { useEffect, useState } from 'react';
import { View, Text, TouchableOpacity, ActivityIndicator } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { contextService, ContextItem } from '../../services/context';

export type DataContext = string; // Was 'auto' | ... now just string to support dynamic

interface ContextSelectorProps {
    context: DataContext;
    onSelect: (context: DataContext) => void;
}

// Default config for Auto and fallbacks
const DEFAULT_CONFIG: Record<string, Partial<ContextItem>> = {
    auto: {
        name: 'auto',
        display_name: 'Auto',
        description: 'ตรวจจับอัตโนมัติ',
        icon: 'flash' as any,
        color: '#8B5CF6' // purple
    },
    revenue: {
        icon: 'trending-up' as any,
        color: '#10B981' // green
    },
    expense: {
        icon: 'trending-down' as any,
        color: '#EF4444' // red
    }
};

const getContextStyle = (name: string) => {
    // 1. Try default config
    if (DEFAULT_CONFIG[name]) return DEFAULT_CONFIG[name];

    // 2. Fallback for new contexts (e.g. transfer_price)
    // Generate distinct colors or rotate? For now use Blue
    return {
        icon: 'layers' as any,
        color: '#3B82F6' // blue
    };
};

export const ContextSelector = ({ context, onSelect }: ContextSelectorProps) => {
    const [contexts, setContexts] = useState<ContextItem[]>([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        loadContexts();
    }, []);

    const loadContexts = async () => {
        try {
            const data = await contextService.fetchContexts();
            setContexts(data);
        } catch (e) {
            console.error(e);
        } finally {
            setLoading(false);
        }
    };

    // Merge Auto + API Contexts
    const allContexts = [
        { ...DEFAULT_CONFIG.auto, id: 'auto' } as ContextItem,
        ...contexts
    ];

    if (loading && contexts.length === 0) {
        return <ActivityIndicator size="small" className="ml-2" />;
    }

    return (
        <View className="flex-row bg-gray-100 dark:bg-gray-800 rounded-full p-1 border border-gray-200 dark:border-gray-700 flex-wrap">
            {allContexts.map((ctx) => {
                const style = getContextStyle(ctx.name);
                const isSelected = context === ctx.name;
                const iconName = ctx.icon || style.icon || 'layers';
                const color = ctx.color || style.color || '#6B7280';

                return (
                    <TouchableOpacity
                        key={ctx.name}
                        onPress={() => onSelect(ctx.name)}
                        className={`px-2.5 py-1.5 rounded-full flex-row items-center gap-1 mb-1 mr-1 ${isSelected ? 'bg-white dark:bg-gray-600 shadow-sm' : ''
                            }`}
                    >
                        <Ionicons
                            name={iconName as any}
                            size={14}
                            color={isSelected ? color : '#9CA3AF'}
                        />
                        <Text
                            className={`text-xs font-medium ${isSelected
                                ? 'text-gray-900 dark:text-white'
                                : 'text-gray-500 dark:text-gray-400'
                                }`}
                        >
                            {ctx.display_name}
                        </Text>
                    </TouchableOpacity>
                );
            })}

            {/* Refresh Button */}
            <TouchableOpacity
                onPress={async () => {
                    setLoading(true);
                    try {
                        await contextService.refreshMetadata();
                        await loadContexts();
                    } catch (e) {
                        console.error(e);
                        setLoading(false);
                    }
                }}
                className="px-2 py-1.5 rounded-full flex-row items-center gap-1 mb-1 mr-1 bg-gray-200 dark:bg-gray-700 active:bg-gray-300"
            >
                <Ionicons name="refresh" size={12} color="#6B7280" />
            </TouchableOpacity>
        </View>
    );
};

// Badge component to show current context in chat
export const ContextBadge = ({ context }: { context: DataContext }) => {
    // We might not have the full list here if it's just a stateless badge.
    // Ideally we pass the full context object, but string is lighter.
    // For now, fast lookup against defaults, fallback to generic.

    // Note: If we really want exact display name for custom contexts here, 
    // we assume the parent/chat has it or we just use the ID capitalized as fallback.

    const style = getContextStyle(context);
    const label = DEFAULT_CONFIG[context]?.display_name || context.charAt(0).toUpperCase() + context.slice(1);
    const color = style.color || '#6B7280';
    const icon = style.icon || 'layers';

    return (
        <View
            className="flex-row items-center gap-1 px-2 py-1 rounded-full"
            style={{ backgroundColor: `${color}20` }}
        >
            <Ionicons name={icon as any} size={12} color={color} />
            <Text style={{ color: color }} className="text-xs font-medium">
                {label}
            </Text>
        </View>
    );
};
