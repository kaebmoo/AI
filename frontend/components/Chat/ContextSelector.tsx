import React, { useEffect, useState } from 'react';
import { Text, TouchableOpacity, ActivityIndicator } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { contextService, ContextItem } from '../../services/context';
import { DropdownPill, DropdownItem } from './DropdownPill';

export type DataContext = string; // 'auto' or any context name from the backend

interface ContextSelectorProps {
    context: DataContext;
    onSelect: (context: DataContext) => void;
}

const AUTO: DropdownItem = { key: 'auto', label: 'Auto', description: 'ตรวจจับอัตโนมัติ', icon: 'flash', color: '#8B5CF6' };

// Icon/colour for contexts the backend does not describe itself
const KNOWN: Record<string, { icon: string; color: string }> = {
    revenue: { icon: 'trending-up', color: '#10B981' },
    expense: { icon: 'trending-down', color: '#EF4444' },
};

const toItem = (c: ContextItem): DropdownItem => ({
    key: c.name,
    label: c.display_name,
    description: c.description,
    icon: c.icon || KNOWN[c.name]?.icon || 'layers',
    color: c.color || KNOWN[c.name]?.color || '#3B82F6',
});

export const ContextSelector = ({ context, onSelect }: ContextSelectorProps) => {
    const [contexts, setContexts] = useState<ContextItem[]>([]);
    const [loading, setLoading] = useState(true);

    const loadContexts = async () => {
        try {
            setContexts(await contextService.fetchContexts());
        } catch (e) {
            console.error(e);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        loadContexts();
    }, []);

    const refresh = async () => {
        setLoading(true);
        try {
            await contextService.refreshMetadata();
        } catch (e) {
            console.error(e);
        }
        await loadContexts();
    };

    if (loading && contexts.length === 0) {
        return <ActivityIndicator size="small" className="ml-2" />;
    }

    return (
        <DropdownPill
            title="แหล่งข้อมูล"
            items={[AUTO, ...contexts.map(toItem)]}
            selected={context}
            onSelect={onSelect}
            footer={
                <TouchableOpacity
                    onPress={refresh}
                    accessibilityRole="button"
                    className="flex-row items-center gap-2 px-4 py-2.5 border-t border-gray-200 dark:border-gray-700"
                >
                    <Ionicons name="refresh" size={14} color="#6B7280" />
                    <Text className="text-xs text-gray-500 dark:text-gray-400">
                        {loading ? 'กำลังโหลด...' : 'โหลดรายการใหม่'}
                    </Text>
                </TouchableOpacity>
            }
        />
    );
};
