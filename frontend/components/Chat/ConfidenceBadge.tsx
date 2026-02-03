import React, { useState } from 'react';
import { View, Text, TouchableOpacity, Animated } from 'react-native';
import { useColorScheme } from '@/hooks/use-color-scheme';

export interface ConfidenceFactor {
    name: string;
    score: number;
    max: number;
    detail: string;
}

export interface ConfidenceData {
    score: number;
    max_score?: number;
    level: 'high' | 'medium' | 'low' | 'very_low';
    level_th: string;
    color: 'green' | 'yellow' | 'orange' | 'red';
    factors: ConfidenceFactor[];
    recommendation: string;
    summary?: string;
}

interface ConfidenceBadgeProps {
    confidence: ConfidenceData;
    compact?: boolean;
}

const colorMap = {
    green: {
        bg: 'bg-emerald-50 dark:bg-emerald-900/20',
        border: 'border-emerald-200 dark:border-emerald-800',
        text: 'text-emerald-700 dark:text-emerald-300',
        icon: 'text-emerald-500',
        bar: 'bg-emerald-500',
        label: 'bg-emerald-100 dark:bg-emerald-900/40',
    },
    yellow: {
        bg: 'bg-amber-50 dark:bg-amber-900/20',
        border: 'border-amber-200 dark:border-amber-800',
        text: 'text-amber-700 dark:text-amber-300',
        icon: 'text-amber-500',
        bar: 'bg-amber-500',
        label: 'bg-amber-100 dark:bg-amber-900/40',
    },
    orange: {
        bg: 'bg-orange-50 dark:bg-orange-900/20',
        border: 'border-orange-200 dark:border-orange-800',
        text: 'text-orange-700 dark:text-orange-300',
        icon: 'text-orange-500',
        bar: 'bg-orange-500',
        label: 'bg-orange-100 dark:bg-orange-900/40',
    },
    red: {
        bg: 'bg-red-50 dark:bg-red-900/20',
        border: 'border-red-200 dark:border-red-800',
        text: 'text-red-700 dark:text-red-300',
        icon: 'text-red-500',
        bar: 'bg-red-500',
        label: 'bg-red-100 dark:bg-red-900/40',
    },
};

const iconMap = {
    high: { icon: '✓', label: 'shield-check' },
    medium: { icon: '!', label: 'alert-circle' },
    low: { icon: '?', label: 'help-circle' },
    very_low: { icon: '✗', label: 'x-circle' },
};

export const ConfidenceBadge = ({ confidence, compact = false }: ConfidenceBadgeProps) => {
    const [expanded, setExpanded] = useState(false);
    const colorScheme = useColorScheme();
    const isDark = colorScheme === 'dark';

    const colors = colorMap[confidence.color] || colorMap.yellow;
    const iconInfo = iconMap[confidence.level] || iconMap.medium;
    const maxScore = confidence.max_score || 100;
    const percentage = Math.round((confidence.score / maxScore) * 100);

    if (compact) {
        // Compact badge - just shows score and level
        return (
            <View className={`flex-row items-center px-2 py-1 rounded-full ${colors.label} ${colors.border} border`}>
                <Text className={`text-xs font-bold mr-1 ${colors.text}`}>
                    {confidence.score}%
                </Text>
                <Text className={`text-xs ${colors.text}`}>
                    {confidence.level_th}
                </Text>
            </View>
        );
    }

    return (
        <View className={`mt-4 rounded-xl border ${colors.bg} ${colors.border}`}>
            {/* Header - Clickable to expand */}
            <TouchableOpacity
                onPress={() => setExpanded(!expanded)}
                className="flex-row items-center justify-between px-4 py-3"
                activeOpacity={0.7}
            >
                <View className="flex-row items-center flex-1">
                    {/* Icon Circle */}
                    <View className={`w-8 h-8 rounded-full items-center justify-center mr-3 ${colors.label}`}>
                        <Text className={`text-base font-bold ${colors.icon}`}>
                            {iconInfo.icon}
                        </Text>
                    </View>

                    {/* Score and Label */}
                    <View className="flex-1">
                        <View className="flex-row items-baseline">
                            <Text className={`text-2xl font-bold ${colors.text}`}>
                                {confidence.score}
                            </Text>
                            <Text className={`text-sm ml-1 ${colors.text} opacity-70`}>
                                / {maxScore}
                            </Text>
                        </View>
                        <Text className={`text-xs ${colors.text} opacity-80`}>
                            ความมั่นใจ: {confidence.level_th}
                        </Text>
                    </View>
                </View>

                {/* Expand/Collapse indicator */}
                <Text className={`text-sm ${colors.text}`}>
                    {expanded ? '▲' : '▼'}
                </Text>
            </TouchableOpacity>

            {/* Progress Bar */}
            <View className="px-4 pb-3">
                <View className="h-2 rounded-full bg-gray-200 dark:bg-gray-700 overflow-hidden">
                    <View
                        className={`h-full rounded-full ${colors.bar}`}
                        style={{ width: `${percentage}%` }}
                    />
                </View>
            </View>

            {/* Expanded Content */}
            {expanded && (
                <View className="border-t border-gray-200 dark:border-gray-700">
                    {/* Factors */}
                    <View className="px-4 py-3">
                        <Text className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide mb-2">
                            ปัจจัยที่ใช้คำนวณ
                        </Text>
                        {confidence.factors.map((factor, index) => (
                            <View key={index} className="mb-2">
                                <View className="flex-row justify-between items-center mb-1">
                                    <Text className="text-sm text-gray-700 dark:text-gray-300 font-medium">
                                        {factor.name}
                                    </Text>
                                    <Text className={`text-sm font-semibold ${
                                        factor.score === factor.max
                                            ? 'text-emerald-600 dark:text-emerald-400'
                                            : factor.score >= factor.max * 0.5
                                                ? 'text-amber-600 dark:text-amber-400'
                                                : 'text-red-600 dark:text-red-400'
                                    }`}>
                                        {factor.score >= 0 ? '+' : ''}{factor.score}
                                    </Text>
                                </View>
                                <Text className="text-xs text-gray-500 dark:text-gray-400">
                                    {factor.detail}
                                </Text>
                                {/* Mini progress bar for each factor */}
                                {factor.max > 0 && (
                                    <View className="h-1 rounded-full bg-gray-200 dark:bg-gray-700 mt-1 overflow-hidden">
                                        <View
                                            className={`h-full rounded-full ${
                                                factor.score === factor.max
                                                    ? 'bg-emerald-500'
                                                    : factor.score >= factor.max * 0.5
                                                        ? 'bg-amber-500'
                                                        : 'bg-red-500'
                                            }`}
                                            style={{ width: `${Math.max(0, (factor.score / factor.max) * 100)}%` }}
                                        />
                                    </View>
                                )}
                            </View>
                        ))}
                    </View>

                    {/* Recommendation */}
                    <View className={`mx-4 mb-4 p-3 rounded-lg ${colors.label}`}>
                        <View className="flex-row items-start">
                            <Text className="mr-2">💡</Text>
                            <Text className={`flex-1 text-sm ${colors.text}`}>
                                {confidence.recommendation}
                            </Text>
                        </View>
                    </View>
                </View>
            )}
        </View>
    );
};

// Compact inline version for use in headers or compact views
export const ConfidenceChip = ({ confidence }: { confidence: ConfidenceData }) => {
    const colors = colorMap[confidence.color] || colorMap.yellow;

    return (
        <View className={`flex-row items-center px-2.5 py-1 rounded-full ${colors.label} border ${colors.border}`}>
            <View className={`w-2 h-2 rounded-full mr-1.5 ${colors.bar}`} />
            <Text className={`text-xs font-semibold ${colors.text}`}>
                {confidence.score}% {confidence.level_th}
            </Text>
        </View>
    );
};
